#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h> // For mutex if needed later
#include <unistd.h>  // For sleep()
#include <pthread.h>

// OpenSSL Headers
#include <openssl/engine.h>
#include <openssl/rand.h>
#include <openssl/err.h>
#include <openssl/evp.h> // For Base64 decoding

// Libcurl Headers
#include <curl/curl.h>

// Jansson Headers (Optional - Recommended)
// #include <jansson.h> // Uncomment if using jansson


/*
Structura pentru argumentele threadurilor de conectare
Este folosita pentru a pasa argumentele necesare
threadurilor care fac conexiunile simultane
la nodurile Alice si Bob.
*/
typedef struct
{
    char *url;          // url-ul lui alice / bob
    char *key_handle;   // key_handle-ul sesiunii QKD
} connect_args_t;


static char *perform_post(const char *url, const char *post_data, char **handle_out, unsigned char **key_out, size_t *key_len_out);

/*
Functie executata de threadurile de conectare

este rulata in paralel pentru a apela /qkd_connect_blocking
pe ambele noduri (Alice si Bob) simultan.

argȘ pointer catre structura connect_args_t cu url si keyhanndle
*/
void *connect_node(void *arg)
{
    connect_args_t *args = (connect_args_t *)arg;

    char *connect_url = NULL;
    char *connect_payload = NULL;
    char *connect_response = NULL;

    // construieste url-ul pt connect_blocking
    // Note: asprintf este o functie care construieste un string, alocand
    // automat memorie pentru el. Daca alocarea esueaza, returneaza NULL.
    if (asprintf(&connect_url, "%s/qkd_connect_blocking", args->url) < 0)
        return NULL; 

    if (asprintf(&connect_payload, "{\"key_handle\": \"%s\"}", args->key_handle) < 0)
    {
        free(connect_url);
        return NULL;
    }

    printf("Template Engine: Connecting node %s...\n", args->url);
    // apeleaza connect blocking pe nodul specificat
    connect_response = perform_post(connect_url, connect_payload, NULL, NULL, NULL);

    //curata memoria
    free(connect_url);
    free(connect_payload);

    if (connect_response)
        free(connect_response);

    return NULL;
}

/* --- Engine Identification --- */
static const char *engine_template_id = "template";                          // Changed ID
static const char *engine_template_name = "Template Engine for OpenSSL RNG"; // Changed Name

/* --- Configuration & State --- */
// NOTE: Using static globals is simpler for an example but NOT thread-safe
// without mutexes. Proper implementation should use ENGINE_set_ex_data.
static char *qkd_service_url = NULL;
static char *qkd_key_handle = NULL;
static unsigned char *qkd_key_buffer = NULL;
static size_t qkd_key_buffer_len = 0;
static size_t qkd_key_buffer_pos = 0;
// static pthread_mutex_t template_lock = PTHREAD_MUTEX_INITIALIZER; // Add if threading needed

/* --- Libcurl write callback --- */
struct MemoryStruct
{
    char *memory;
    size_t size;
};

/*
Functie de callback pentru libcurl - primirea datelor http
Functia este apelata de libcurl pentru fiecare bucata de date
primita din raspunsul http. Realoca memoria pentru a stoca datele
content: pointer catre datele primite
size: dimensiunea unui element
nmemb: numarul de elemente primite
userp: pointer catre structura MemoryStruct in care se stocheaza datele
Returneaza numarul de bytes procesati (size * nmemb)
*/
static size_t WriteMemoryCallback(void *contents, size_t size, size_t nmemb, void *userp)
{
    size_t realsize = size * nmemb;
    struct MemoryStruct *mem = (struct MemoryStruct *)userp;

    // realoca memoria pentru a include noile date
    char *ptr = realloc(mem->memory, mem->size + realsize + 1);
    if (ptr == NULL)
    {
        fprintf(stderr, "Template Engine: not enough memory (realloc returned NULL)\n");
        return 0;
    }

    // copiaza noile date in buffer
    mem->memory = ptr;
    memcpy(&(mem->memory[mem->size]), contents, realsize);
    mem->size += realsize;
    mem->memory[mem->size] = 0; // terminatorul NULL

    return realsize;
}

/* --- Helper: Perform HTTP POST --- */

/*
Functie principala pentru cererile http POST
Functia realizeaza cererile post catre api-ul QKD
si pastreaza raspunsurile json pentru a extrage key_handle sau key_buffer.

url: endpoint-ul QKD
post_data: payload-ul JSON pentru cererea POST
handle_out: pointer catre un buffer in care se va stoca key_handle (poate fi NULL)
key_out: pointer catre un buffer in care se va stoca cheia decodificata (poate fi NULL)
key_len_out: pointer cpentru a stoca dimensiunea cheii (poate fi NULL)

Returneaza raspunsul HTTP complet (trebuie eliberat de apelant) sau null in caz de eroare.
*/
static char *perform_post(const char *url, const char *post_data, char **handle_out, unsigned char **key_out, size_t *key_len_out)
{
    CURL *curl;
    CURLcode res;
    struct MemoryStruct chunk;
    char *response_body = NULL; // Store the full response if needed

    // initializarea buffer-ului pentru raspuns
    chunk.memory = malloc(1); // Will be grown by realloc
    chunk.size = 0;

    //initializarea libcurl
    curl = curl_easy_init();
    if (!curl)
    {
        fprintf(stderr, "Template Engine: curl_easy_init() failed\n");
        free(chunk.memory);
        return NULL;
    }

    // configurarea headerelor HTTP
    struct curl_slist *headers = NULL;
    headers = curl_slist_append(headers, "Content-Type: application/json");

    // configureaza optiunile curl
    curl_easy_setopt(curl, CURLOPT_URL, url);   // set url
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, post_data); // set payload
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteMemoryCallback); // set callback pentru raspuns
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, (void *)&chunk);  // set data pointer
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);    // set header
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "template-openssl-engine/1.0"); // Changed agent
    // user agent-ul este setat pentru a identifica engine-ul,
    // este o practica buna


    // executarea cererii HTTP
    res = curl_easy_perform(curl);

    if (res != CURLE_OK)
    {
        fprintf(stderr, "Template Engine: curl_easy_perform() failed: %s\n", curl_easy_strerror(res));
        free(chunk.memory);
        curl_slist_free_all(headers);
        curl_easy_cleanup(curl);
        return NULL;
    }

    // verificarea codului de status http
    long http_code = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);

    // clean la resurse
    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    // daca codul nu e succes, afisam o erroare
    if (http_code != 200)
    {
        fprintf(stderr, "Template Engine: HTTP request failed with code %ld. Response: %s\n", http_code, chunk.memory ? chunk.memory : "N/A");
        free(chunk.memory);
        return NULL;
    }

    // Minimal JSON parsing (teoretic, ar trebui sa folosesc o biblioteca json dedicata)
    if (chunk.memory)
    {
        response_body = chunk.memory; // Keep the response

        // extrage key_hanfle din raspuns (pentru qkd_open)
        if (handle_out)
        {
            char *p = strstr(response_body, "\"key_handle\"");
            if (p)
            {
                p = strchr(p + 12, '"'); // caut prima ghilimea de dupa "key_handle"
                if (p)
                {
                    p++; // skip la prima ghilimea ca sa pointam de la inceputul valorii
                    char *q = strchr(p, '"'); // caut ghilimeaua de final
                    if (q)
                    {
                        size_t len = q - p; // lungimea valorii
                        *handle_out = malloc(len + 1); // aloc memorie pt key_handle
                        if (*handle_out)    // daca alocarea a reusit
                        {
                            strncpy(*handle_out, p, len); // copiez valoarea in buffer
                            (*handle_out)[len] = '\0';
                        }
                    }
                }
            }
            if (!*handle_out)
                fprintf(stderr, "Template Engine: Failed to parse 'key_handle'\n");
        }
        // extragem si decodificam key_buffer din raspuns (pentru qkd_get_key)
        else if (key_out && key_len_out) // daca am primit pointerii pentru key_out si key_len_out
        {// la fel ca mai sus, cautam in raspuns
            char *p = strstr(response_body, "\"key_buffer\"");
            if (p)
            {
                p = strchr(p + 12, '"'); // caut prima ghilimea de dupa "key_buffer"
                if (p)
                {
                    p++; // skip la ghilimea
                    char *q = strchr(p, '"'); // caut ghilimeaua de final
                    if (q)
                    {
                        size_t hex_len = q - p; // lungimea hex-ului
                        *key_len_out = hex_len / 2; // lungimea in bytes (2 hex = 1 byte)
                        *key_out = malloc(*key_len_out); // aloc memorie pentru cheia decodificata
                        if (*key_out)
                        {
                            // convertesc fiecare pereche de hex in byte
                            for (size_t i = 0; i < *key_len_out; i++)
                            {
                                sscanf(&p[i * 2], "%2hhx", &((*key_out)[i]));
                            }
                        }
                        else
                        {
                            fprintf(stderr, "Template Engine: malloc failed for key_out.\n");
                            *key_len_out = 0;
                        }
                    }
                }
            }
            if (!*key_out)
                fprintf(stderr, "Template Engine: Failed to parse 'key_buffer'\n");
        }
    }
    else
    {
        fprintf(stderr, "Template Engine: No response body received.\n");
        return NULL;
    }
    return response_body;
}

/*
Functie de conectare la sistemul qkd

aceasta functie initiaza conexiunea la sitemul qkd, urmarind cam ce se intampla si
in fisierul test.py

1. apeleaza open pe alice pentru key_handle
2. apeleaza connect_blocking pe ambele noduri in paralel
*/
static int template_engine_connect()
{
    if (!qkd_service_url)
    {
        fprintf(stderr, "Template Engine: Service URL not set.\n");
        return -1;
    }

    // pasul 1: deschiderea conexiunii QKD (Alice)
    char *open_url = NULL;
    char *open_response = NULL;

    // construim url-ul pentru /qkd_open
    if (asprintf(&open_url, "%s/qkd_open", qkd_service_url) < 0)
        return -1;

    printf("Template Engine: Opening connection via %s...\n", open_url);

    // apelam qkd_open cu un payload gol pentru a obtine key_handle
    open_response = perform_post(open_url, "{}", &qkd_key_handle, NULL, NULL);
    free(open_url);

    if (!open_response || !qkd_key_handle)
    {
        fprintf(stderr, "Template Engine: Failed to open QKD connection.\n");
        free(open_response);
        return -1;
    }
    printf("Template Engine: Got Key Handle: %s\n", qkd_key_handle);
    free(open_response);


    // pasul 2: conectarea la nodurile Alice si Bob in paralel
    printf("Template Engine: Starting parallel connections for Alice and Bob...\n");

    pthread_t alice_thread, bob_thread;

    // argumentele pentru threadurile de conectare
    connect_args_t alice_args = {qkd_service_url, qkd_key_handle};
    connect_args_t bob_args = {"http://z2w.local:5000", qkd_key_handle}; // aici am hardcodat, stiu, urat din partea mea :(

    // porneste threadul lui Alice
    if (pthread_create(&alice_thread, NULL, connect_node, &alice_args) != 0)
    {
        fprintf(stderr, "Template Engine: Failed to create Alice thread\n");
        goto connect_err;
    }

    // porneste threadul lui Bob
    if (pthread_create(&bob_thread, NULL, connect_node, &bob_args) != 0)
    {
        fprintf(stderr, "Template Engine: Failed to create Bob thread\n");

        pthread_cancel(alice_thread);
        goto connect_err;
    }

    // asteptam finalizarea threadurilor
    printf("Template Engine: Waiting for connection threads to complete...\n");
    pthread_join(alice_thread, NULL);
    pthread_join(bob_thread, NULL);
    printf("Template Engine: Both nodes connected successfully.\n");

    return 0; // Success

connect_err:
    // gestionarea erorilor si curatarea resurselor
    fprintf(stderr, "Template Engine: Error during parallel connect phase.\n");
    if (qkd_key_handle)
    {
        // incearca sa inchida conexiunile daca a fost deschisa
        char *close_url = NULL, *close_payload = NULL;
        if (asprintf(&close_url, "%s/qkd_close", qkd_service_url) >= 0 &&
            asprintf(&close_payload, "{\"key_handle\": \"%s\"}", qkd_key_handle) >= 0)
        {
            printf("Template Engine: Attempting cleanup close...\n");
            char *close_resp = perform_post(close_url, close_payload, NULL, NULL, NULL);
            free(close_resp);
        }
        free(close_url);
        free(close_payload);
        free(qkd_key_handle);
        qkd_key_handle = NULL;
    }
    return -1;
}

/*
functie de obtinere a unei noi chei qkd

Solicita cheia de la QuPinet prin apelearea /qkd_get_key
include un mecanism de retry pentru a astepta pana cand
cheia este generata complet (transmiting -> ready)

returneaza 0 pentru succes, -1 pentru erroare
*/
static int template_engine_fetch_key()
{
    if (!qkd_service_url || !qkd_key_handle)
    {
        fprintf(stderr, "Template Engine: Not connected.\n");
        return -1;
    }

    // curatam bufferul vechi, daca exista
    free(qkd_key_buffer);
    qkd_key_buffer = NULL;
    qkd_key_buffer_len = 0;
    qkd_key_buffer_pos = 0;

    // configuram mecanismul de retry
    const int MAX_RETRY_ATTEMPTS = 30; // Maximum number of retry attempts
    const int RETRY_DELAY_SECONDS = 2; // Delay between retries
    int retry_count = 0;

    // bucla de retry pentru asteptarea cheii
    while (retry_count < MAX_RETRY_ATTEMPTS)
    {
        char *get_key_url = NULL;
        char *get_key_payload = NULL;
        char *get_key_response = NULL;

        // construieste cererea pentru qkd_get_key
        // teoretic puteam sa o fac inafara whileului, dar for safety o fac in while
        // nu moare nimeni daca le reconstruiesc in while :)
        if (asprintf(&get_key_url, "%s/qkd_get_key", qkd_service_url) < 0)
            return -1;
        if (asprintf(&get_key_payload, "{\"key_handle\": \"%s\"}", qkd_key_handle) < 0)
        {
            free(get_key_url);
            return -1;
        }

        // pentru a evita spam-ul in logs, afisez doar prima incercare si la fiecare 5 incercari
        if (retry_count == 0 || retry_count % 5 == 0)
            printf("Template Engine: Fetching key via %s... (attempt %d/%d)\n",
                   get_key_url, retry_count + 1, MAX_RETRY_ATTEMPTS);

        // incearca sa obtina cheia 
        get_key_response = perform_post(get_key_url, get_key_payload, NULL, &qkd_key_buffer, &qkd_key_buffer_len);
        free(get_key_url);
        free(get_key_payload);

        // verific succesul, adica am un raspuns si bufferul are ceva in el
        if (get_key_response && qkd_key_buffer && qkd_key_buffer_len > 0)
        {
            printf("Template Engine: Successfully fetched %zu bytes of key material after %d attempt(s).\n",
                   qkd_key_buffer_len, retry_count + 1);
            free(get_key_response);
            qkd_key_buffer_pos = 0; // reseteaza pozitia in buffer (se modifica in rand_bytes)
            return 0; // succes
        }

        // curatam raspunsul partial/bufferul
        free(get_key_response);
        free(qkd_key_buffer);
        qkd_key_buffer = NULL;
        qkd_key_buffer_len = 0;

        // daca am ajuns aici, cheia nu este gata ( ar fi iesit la return succes )
        retry_count++;

        // daca am atins maximul, dam break
        if (retry_count >= MAX_RETRY_ATTEMPTS)
        {
            fprintf(stderr, "Template Engine: Failed to get key after %d attempts.\n", MAX_RETRY_ATTEMPTS);
            break;
        }

        // asteptam inainte de retrying
        printf("Template Engine: Key not ready yet, waiting %d seconds before retry %d/%d...\n",
               RETRY_DELAY_SECONDS, retry_count + 1, MAX_RETRY_ATTEMPTS);
        sleep(RETRY_DELAY_SECONDS);
    }

    // toate incercarile au esuat
    fprintf(stderr, "Template Engine: Failed to get key or key is empty after all retry attempts.\n");
    return -1;
}

/*
Functie de inchidere a conexiunii

curata toate resursele asociate cu conexiunea qkd
inclusiv apelarea /qkd_close pentru a notifica sistemul QKD
*/
static void template_engine_close()
{
    // se incearca incgiderea conexiunii daca avem handle si url
    if (qkd_key_handle && qkd_service_url)
    {
        char *close_url = NULL;
        char *close_payload = NULL;

        // construim cererea de inchidere
        if (asprintf(&close_url, "%s/qkd_close", qkd_service_url) >= 0 && asprintf(&close_payload, "{\"key_handle\": \"%s\"}", qkd_key_handle) >= 0)
        {
            printf("Template Engine: Closing connection (handle: %s)...\n", qkd_key_handle);
            char *close_resp = perform_post(close_url, close_payload, NULL, NULL, NULL);
            free(close_resp);
        }
        free(close_url);
        free(close_payload);
        free(qkd_key_handle);
        qkd_key_handle = NULL;
    }
    // curatam bufferul de chei
    free(qkd_key_buffer);
    qkd_key_buffer = NULL;
    qkd_key_buffer_len = 0;
    qkd_key_buffer_pos = 0;
}

/*
Implementarea RAND_METHOD: SEED

In engineul asta, nu acceptam seeding extern deoarece
bitii vin direct din QuPiNet. Pur si simplu ii facem un stub
*/
static int template_rand_seed(const void *buf, int num)
{
    printf("Template Engine: RAND_METHOD seed (no-op).\n");
    return 1; // Indicate success
}

/*
Implementarea RAND_METHOD: BYTES (functia principala)

Functia furnizeaza octetii aleatori catre openssl, gestioneaza buffer-ul intern de chei
si solicita noi chei cand este necesar

buf: bufferul unde scriem octetii pentru cheie
num: numarul de octeti ceruti de openssl
returneaza 1 pentru succes 0 pentru esec
*/
static int template_rand_bytes(unsigned char *buf, int num)
{
    int bytes_provided = 0;

    // conectarea automata la prima apelare
    if (!qkd_key_handle)
    {
        printf("Template Engine: First call to rand_bytes, attempting connection...\n");
        if (template_engine_connect() != 0)
        {
            fprintf(stderr, "Template Engine: Connection failed during rand_bytes.\n");
            return 0;
        }
    }

    // bucla principala pentru obtinerea octetilor
    while (bytes_provided < num)
    {
        // verificam daca bufferul este gol sau empty
        if (qkd_key_buffer_pos >= qkd_key_buffer_len)
        {
            printf("Template Engine: Key buffer empty, fetching new key...\n");
            if (template_engine_fetch_key() != 0)
            {
                fprintf(stderr, "Template Engine: Failed fetch new key.\n");
                return (bytes_provided > 0); //returneaza partial daca am furnizat ceva
            }
            if (qkd_key_buffer_len == 0)
            {
                fprintf(stderr, "Template Engine: Fetched 0 bytes.\n");
                return (bytes_provided > 0);
            }
        }

        // calculez cati octeti trb copiati
        size_t bytes_to_copy = qkd_key_buffer_len - qkd_key_buffer_pos; //bytes disponibil
        int bytes_needed = num - bytes_provided; // inca necesari
        if (bytes_to_copy > bytes_needed)
        {
            bytes_to_copy = bytes_needed; // nu copia mai mult decat este necesar
        }

        // copiaza octetii in buffer
        memcpy(buf + bytes_provided, qkd_key_buffer + qkd_key_buffer_pos, bytes_to_copy);
        qkd_key_buffer_pos += bytes_to_copy; // actualizeaza pozitia in buffer
        bytes_provided += bytes_to_copy;     // actualizeaza octetii total furnizati

        /*
        Poate apare intrebarea, de ce se incearca mai multe obtineri de cheie?
        Cheia e una si buna, nu?
        Ei bine, daca dispozitivul genereaza o cheie de, sa zicem 32 octeti si
        engineul are setat ca parametru ca vrea mai mult de 32 de octeti, sa zicem 64
        Acesta va concatena aceeasi cheie pana ajunge la numarul de biti ceruti.

        As fi putut sa hardcodez treaba asta dar cumva mi s-a parut mai elegant
        */
    }
    return 1; // success
}

/*
Implementarea RAND_METHOD: CLEANUP

Functia este apelata cand engine-ul este descarcat sau
cand openssl nu mai are nevoie de generatorul de numere random
( in cazul nostru, obtinerea cheii )
Inchide conexiunea QKD si curata resursele
*/ 

static void template_rand_cleanup(void)
{
    printf("Template Engine: RAND_METHOD cleanup. Closing connection.\n");
    template_engine_close();
}

// Stub pentru ca QuPiNet se ocupa de tot :P
static int template_rand_add(const void *buf, int num, double entropy)
{
    printf("Template Engine: RAND_METHOD add (no-op).\n");
    return 1;
}

/*
Verifica daca generatorul de numere aleatorii (in cazul nostru, QuPiNet)
este functional. Mai exact verifica daca url-ul serviciului este setat
*/
static int template_rand_status(void)
{
    printf("Template Engine: RAND_METHOD status check.\n");
    int status = (qkd_service_url != NULL);
    return status;
}

// Define the RAND_METHOD structure
static RAND_METHOD template_rand_meth = {
    template_rand_seed,    // seed (int (*)(const void *buf, int num))
    template_rand_bytes,   // bytes (int (*)(unsigned char *buf, int num))
    template_rand_cleanup, // cleanup (void (*)(void))
    template_rand_add,     // add (int (*)(const void *buf, int num, double entropy))
    template_rand_bytes,   // pseudorand_bytes (int (*)(unsigned char *buf, int num))
    template_rand_status   // status (int (*)(void))
};

/* --- Engine Control Commands --- */
/*
 * template_cmd_defns este un array constant de structuri ENGINE_CMD_DEFN care defineste comenzile personalizate
 * suportate de acest ENGINE OpenSSL. Fiecare element specifica un ID numeric, un nume de comanda, o descriere
 * si tipul argumentului asteptat (in acest caz, un string pentru URL-ul serviciului QKD). Ultimul element are
 * valorile nule pentru a marca sfarsitul array-ului.
 */
static const ENGINE_CMD_DEFN template_cmd_defns[] = { 
    {1, "QKD_SERVICE_URL", "Sets the URL for the QKD service", ENGINE_CMD_FLAG_STRING},
    {0, NULL, NULL, 0}}; // valoarea pentru service url e gasita in configuratie


/*
Functia de control a engineului

Functia gestioneaza comenzile de control al engineului, precum
setarea url-ului pentru QKD. Se poate vedea configuratia :)

e: instanta engineului openssl
cmd: codul comenzii
i: nefolosit
p: pointer catre datele comenzii
f: nefolosit (pointer catre o functie)
returneaza 1 pentru succes, 0 pentru esec
*/
static int template_engine_ctrl(ENGINE *e, int cmd, long i, void *p, void (*f)(void))
{
    switch (cmd)
    {
    case 1: // QKD_SERVICE_URL
        if (!p)
        {
            fprintf(stderr, "Template Engine: NULL URL pointer\n");
            return 0;
        }
        // elibereaza url-ul vechi si seteaza unul nou
        free(qkd_service_url);
        qkd_service_url = strdup((const char *)p);
        if (!qkd_service_url)
        {
            fprintf(stderr, "Template Engine: strdup failed\n");
            return 0;
        }
        printf("Template Engine: Set service URL to %s\n", qkd_service_url);
        return 1;
    default:
        break;
    }
    return 0;
}

/*
Functia de distrugere a engine-ului

este apelata cand engineul este unloaded din OpenSSL
curata resursele alocate

e: instanta engineului
1 daca e success
*/
static int template_engine_destroy(ENGINE *e)
{
    printf("Template Engine: Destroying.\n");
    template_engine_close();
    free(qkd_service_url);
    qkd_service_url = NULL;
    return 1;
}

/*
functie de initializare a engine-ului

este apelata cand e incarcata in openssl
initializeaza libcurl pt cererile http

e: instanta engineului
returneaza 1 succes, 0 pentru esec
*/
static int template_engine_init(ENGINE *e)
{
    // Initializeaza LibCurl pentru cererile HTTP
    if (curl_global_init(CURL_GLOBAL_ALL))
    {
        fprintf(stderr, "Template Engine: libcurl init failed\n");
        return 0;
    }
    printf("Template Engine: Initializing.\n");
    return 1;
}

/*
Functie de finalizare a engineului

Functia e apelata cand OpenSSL nu mai foloseste engine-ul activ
In cazul nostru, si aceasta functie e stubbed
*/
static int template_engine_finish(ENGINE *e)
{
    printf("Template Engine: Finishing.\n");
    return 1;
}

/*
Functie de legare a engine-ului la openssl

functia configureaza aspectele engineului
-seteaza idul si numele
-asociaza implementarile de mai sus pentru rand_method
-configureaza functiile de control

e: instanta engineului
id: idul engine-ului
returneaza 1 pentru succes, 0 pentru esec
*/
static int bind_helper(ENGINE *e, const char *id)
{
    // Use the template ID and name defined above
    if (!ENGINE_set_id(e, engine_template_id) ||              // seteaza id-ul
        !ENGINE_set_name(e, engine_template_name) ||          // seteaza numele
        !ENGINE_set_RAND(e, &template_rand_meth) ||           // asociez randmethod
        !ENGINE_set_ctrl_function(e, template_engine_ctrl) || // functia de control
        !ENGINE_set_cmd_defns(e, template_cmd_defns) ||       // definitiile comenzilor
        !ENGINE_set_destroy_function(e, template_engine_destroy) || // functia de distrugere
        !ENGINE_set_init_function(e, template_engine_init) ||       // functia de initializare
        !ENGINE_set_finish_function(e, template_engine_finish))     // functia de finalizare
    {
        fprintf(stderr, "Template Engine: Failed to set engine properties.\n");
        return 0;
    }
    printf("Template Engine: bind_helper successful for ID %s\n", engine_template_id);
    return 1;
}

// pentru static linking (mai putin common pt engines)
#ifndef OPENSSL_NO_STATIC_ENGINE
void ENGINE_load_template(void)
{
    // Am incercat ceva, se poate ignora :P
    ENGINE *e = ENGINE_new();
    if (!e)
        return;
    if (!bind_helper(e, engine_template_id))
    { // Use template ID
        ENGINE_free(e);
        return;
    }
    ENGINE_add(e);
    ENGINE_free(e);
    ERR_clear_error();
}
#endif

// Standard dynamic engine loading entry point
IMPLEMENT_DYNAMIC_BIND_FN(bind_helper)
IMPLEMENT_DYNAMIC_CHECK_FN()