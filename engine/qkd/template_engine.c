#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h> // For mutex if needed later

// OpenSSL Headers
#include <openssl/engine.h>
#include <openssl/rand.h>
#include <openssl/err.h>
#include <openssl/evp.h> // For Base64 decoding

// Libcurl Headers
#include <curl/curl.h>

// Jansson Headers (Optional - Recommended)
// #include <jansson.h> // Uncomment if using jansson

/* --- Engine Identification --- */
static const char *engine_template_id = "template"; // Changed ID
static const char *engine_template_name = "Template Engine for OpenSSL RNG"; // Changed Name

/* --- Configuration & State --- */
// NOTE: Using static globals is simpler for an example but NOT thread-safe
// without mutexes. Proper implementation should use ENGINE_set_ex_data.
static char *qkd_service_url = NULL; // Still using QKD logic for this example
static char *qkd_key_handle = NULL;
static unsigned char *qkd_key_buffer = NULL;
static size_t qkd_key_buffer_len = 0;
static size_t qkd_key_buffer_pos = 0;
// static pthread_mutex_t template_lock = PTHREAD_MUTEX_INITIALIZER; // Add if threading needed

/* --- Libcurl write callback --- */
struct MemoryStruct {
    char *memory;
    size_t size;
};

static size_t WriteMemoryCallback(void *contents, size_t size, size_t nmemb, void *userp) {
    size_t realsize = size * nmemb;
    struct MemoryStruct *mem = (struct MemoryStruct *)userp;

    char *ptr = realloc(mem->memory, mem->size + realsize + 1);
    if (ptr == NULL) {
        fprintf(stderr, "Template Engine: not enough memory (realloc returned NULL)\n");
        return 0;
    }

    mem->memory = ptr;
    memcpy(&(mem->memory[mem->size]), contents, realsize);
    mem->size += realsize;
    mem->memory[mem->size] = 0;

    return realsize;
}

/* --- Helper: Perform HTTP POST --- */
// (Keep the perform_post function from the previous example - it's needed for QKD logic)
// Returns the response body string (must be freed by caller) or NULL on error.
// Parses simple JSON for "key_handle" or "key_buffer" if key_out/handle_out != NULL
static char* perform_post(const char *url, const char *post_data, char **handle_out, unsigned char **key_out, size_t *key_len_out) {
    CURL *curl;
    CURLcode res;
    struct MemoryStruct chunk;
    char *response_body = NULL; // Store the full response if needed

    chunk.memory = malloc(1); // Will be grown by realloc
    chunk.size = 0;

    curl = curl_easy_init();
    if (!curl) {
        fprintf(stderr, "Template Engine: curl_easy_init() failed\n");
        free(chunk.memory);
        return NULL;
    }

    struct curl_slist *headers = NULL;
    headers = curl_slist_append(headers, "Content-Type: application/json");

    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, post_data);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteMemoryCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, (void *)&chunk);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "template-openssl-engine/1.0"); // Changed agent

    res = curl_easy_perform(curl);

    if (res != CURLE_OK) {
        fprintf(stderr, "Template Engine: curl_easy_perform() failed: %s\n", curl_easy_strerror(res));
        free(chunk.memory);
        curl_slist_free_all(headers);
        curl_easy_cleanup(curl);
        return NULL;
    }

    long http_code = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);

    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    if (http_code != 200) {
         fprintf(stderr, "Template Engine: HTTP request failed with code %ld. Response: %s\n", http_code, chunk.memory ? chunk.memory : "N/A");
         free(chunk.memory);
         return NULL;
    }

    // Minimal JSON parsing (replace with Jansson for robustness)
    if (chunk.memory) {
        response_body = chunk.memory; // Keep the response
        if (handle_out) {
            // ... (parsing logic for key_handle - unchanged) ...
            char *p = strstr(response_body, "\"key_handle\"");
            if (p) {
                p = strchr(p + 12, '"'); if (p) { p++; char *q = strchr(p, '"'); if (q) {
                    size_t len = q - p; *handle_out = malloc(len + 1); if(*handle_out) { strncpy(*handle_out, p, len); (*handle_out)[len] = '\0'; }
                }}
            }
            if (!*handle_out) fprintf(stderr, "Template Engine: Failed to parse 'key_handle'\n");

        } else if (key_out && key_len_out) {
             // ... (parsing logic for key_buffer - unchanged) ...
            char *p = strstr(response_body, "\"key_buffer\"");
            if (p) {
                p = strchr(p + 12, '"'); if (p) { p++; char *q = strchr(p, '"'); if (q) {
                    size_t base64_len = q - p; *key_out = malloc(base64_len); if (*key_out) {
                        char* base64_str = strndup(p, base64_len); if (base64_str) {
                            *key_len_out = EVP_DecodeBlock(*key_out, (const unsigned char*)base64_str, base64_len); free(base64_str);
                            if ((int)*key_len_out < 0) { fprintf(stderr, "Template Engine: Base64 decode failed.\n"); free(*key_out); *key_out = NULL; *key_len_out = 0; }
                        } else { fprintf(stderr, "Template Engine: strndup failed.\n"); free(*key_out); *key_out = NULL; *key_len_out = 0; }
                    }
                }}
            }
            if (!*key_out) fprintf(stderr, "Template Engine: Failed to parse 'key_buffer'\n");
        }
    } else {
         fprintf(stderr, "Template Engine: No response body received.\n");
         return NULL;
    }
    return response_body;
}


/* --- QKD API Interaction Functions --- */
// Renaming functions for clarity, keeping QKD logic for this example
// Returns 0 on success, -1 on error
static int template_engine_connect() {
    // ... (function logic identical to qkd_engine_connect, just change print messages) ...
    if (!qkd_service_url) { fprintf(stderr, "Template Engine: Service URL not set.\n"); return -1; }

    // Step 1: Open
    char *open_url = NULL; char *open_response = NULL;
    if (asprintf(&open_url, "%s/qkd_open", qkd_service_url) < 0) return -1;
    printf("Template Engine: Opening connection via %s...\n", open_url);
    open_response = perform_post(open_url, "{}", &qkd_key_handle, NULL, NULL); free(open_url);
    if (!open_response || !qkd_key_handle) { fprintf(stderr, "Template Engine: Failed to open QKD connection.\n"); free(open_response); return -1; }
    printf("Template Engine: Got Key Handle: %s\n", qkd_key_handle); free(open_response);

    // Step 2: Connect Blocking
    char *connect_url = NULL; char *connect_payload = NULL; char *connect_response = NULL;
    if (asprintf(&connect_url, "%s/qkd_connect_blocking", qkd_service_url) < 0) goto connect_err;
    if (asprintf(&connect_payload, "{\"key_handle\": \"%s\"}", qkd_key_handle) < 0) goto connect_err;
    printf("Template Engine: Connecting blocking via %s...\n", connect_url);
    connect_response = perform_post(connect_url, connect_payload, NULL, NULL, NULL);
    free(connect_url); free(connect_payload); connect_url = NULL; connect_payload = NULL;
    if (!connect_response) { fprintf(stderr, "Template Engine: Failed to connect blocking.\n"); goto connect_err; }
    printf("Template Engine: Connect blocking successful.\n"); free(connect_response);
    return 0; // Success

connect_err: /* ... (error handling identical to qkd_engine_connect) ... */
    fprintf(stderr, "Template Engine: Error during connect blocking phase.\n");
    free(connect_url); free(connect_payload); free(connect_response);
    if (qkd_key_handle) {
        char *close_url=NULL, *close_payload=NULL;
         if (asprintf(&close_url, "%s/qkd_close", qkd_service_url) >= 0 && asprintf(&close_payload, "{\"key_handle\": \"%s\"}", qkd_key_handle) >= 0) {
            printf("Template Engine: Attempting cleanup close...\n"); char *close_resp = perform_post(close_url, close_payload, NULL, NULL, NULL); free(close_resp);
         } free(close_url); free(close_payload); free(qkd_key_handle); qkd_key_handle = NULL;
    }
    return -1;
}

// Fetches a new key, returns 0 on success, -1 on error
static int template_engine_fetch_key() {
    // ... (function logic identical to qkd_engine_fetch_key, just change print messages) ...
    if (!qkd_service_url || !qkd_key_handle) { fprintf(stderr, "Template Engine: Not connected.\n"); return -1; }
    free(qkd_key_buffer); qkd_key_buffer = NULL; qkd_key_buffer_len = 0; qkd_key_buffer_pos = 0;
    char *get_key_url = NULL; char *get_key_payload = NULL; char *get_key_response = NULL;
    if (asprintf(&get_key_url, "%s/qkd_get_key", qkd_service_url) < 0) return -1;
    if (asprintf(&get_key_payload, "{\"key_handle\": \"%s\"}", qkd_key_handle) < 0) { free(get_key_url); return -1; }
    printf("Template Engine: Fetching key via %s...\n", get_key_url);
    get_key_response = perform_post(get_key_url, get_key_payload, NULL, &qkd_key_buffer, &qkd_key_buffer_len);
    free(get_key_url); free(get_key_payload);
    if (!get_key_response || !qkd_key_buffer || qkd_key_buffer_len == 0) {
        fprintf(stderr, "Template Engine: Failed to get key or key is empty.\n"); free(get_key_response); free(qkd_key_buffer);
        qkd_key_buffer = NULL; qkd_key_buffer_len = 0; return -1;
    }
    printf("Template Engine: Successfully fetched %zu bytes of key material.\n", qkd_key_buffer_len);
    free(get_key_response); qkd_key_buffer_pos = 0; return 0;
}

// Closes connection
static void template_engine_close() {
    // ... (function logic identical to qkd_engine_close, just change print messages) ...
     if (qkd_key_handle && qkd_service_url) {
        char *close_url = NULL; char *close_payload = NULL;
        if (asprintf(&close_url, "%s/qkd_close", qkd_service_url) >= 0 && asprintf(&close_payload, "{\"key_handle\": \"%s\"}", qkd_key_handle) >= 0) {
            printf("Template Engine: Closing connection (handle: %s)...\n", qkd_key_handle);
            char *close_resp = perform_post(close_url, close_payload, NULL, NULL, NULL); free(close_resp);
        } free(close_url); free(close_payload); free(qkd_key_handle); qkd_key_handle = NULL;
    }
    free(qkd_key_buffer); qkd_key_buffer = NULL; qkd_key_buffer_len = 0; qkd_key_buffer_pos = 0;
}


/* --- RAND_METHOD Implementation --- */

// NO ENGINE* parameter, returns int (corrected)
static int template_rand_seed(const void *buf, int num) {
    // We don't actually seed from external source in this engine
    // The "seeding" comes from the QKD API via rand_bytes
    printf("Template Engine: RAND_METHOD seed (no-op).\n");
    return 1; // Indicate success
}

// Correct signature already
static int template_rand_bytes(unsigned char *buf, int num) {
   // ... (logic remains the same) ...
   int bytes_provided = 0;
   if (!qkd_key_handle) {
       printf("Template Engine: First call to rand_bytes, attempting connection...\n");
       if (template_engine_connect() != 0) {
            fprintf(stderr, "Template Engine: Connection failed during rand_bytes.\n"); return 0;
       }
   }
   while (bytes_provided < num) {
       if (qkd_key_buffer_pos >= qkd_key_buffer_len) {
           printf("Template Engine: Key buffer empty, fetching new key...\n");
           if (template_engine_fetch_key() != 0) {
               fprintf(stderr, "Template Engine: Failed fetch new key.\n"); return (bytes_provided > 0);
           }
            if (qkd_key_buffer_len == 0) { fprintf(stderr, "Template Engine: Fetched 0 bytes.\n"); return (bytes_provided > 0); }
       }
       size_t bytes_to_copy = qkd_key_buffer_len - qkd_key_buffer_pos;
       int bytes_needed = num - bytes_provided;
       if (bytes_to_copy > bytes_needed) { bytes_to_copy = bytes_needed; }
       memcpy(buf + bytes_provided, qkd_key_buffer + qkd_key_buffer_pos, bytes_to_copy);
       qkd_key_buffer_pos += bytes_to_copy;
       bytes_provided += bytes_to_copy;
   }
   return 1; // Indicate success
}

// NO ENGINE* parameter, returns void (this one was correct)
static void template_rand_cleanup(void) {
   printf("Template Engine: RAND_METHOD cleanup. Closing connection.\n");
   template_engine_close();
    // No return value needed
}

// NO ENGINE* parameter, returns int (corrected)
static int template_rand_add(const void *buf, int num, double entropy) {
   // This engine gets entropy from QKD, doesn't accept external additions
   printf("Template Engine: RAND_METHOD add (no-op).\n");
   return 1; // Indicate success
}

// NO ENGINE* parameter
static int template_rand_status(void) {
   printf("Template Engine: RAND_METHOD status check.\n");
   // Status depends on whether the URL is set (and maybe if connected?)
   int status = (qkd_service_url != NULL);
   // Potentially add: && qkd_key_handle != NULL
   return status;
}


// Define the RAND_METHOD structure (Now matches the corrected functions)
static RAND_METHOD template_rand_meth = {
   template_rand_seed,      // seed (int (*)(const void *buf, int num)) - corrected expected type
   template_rand_bytes,     // bytes (int (*)(unsigned char *buf, int num))
   template_rand_cleanup,   // cleanup (void (*)(void))
   template_rand_add,       // add (int (*)(const void *buf, int num, double entropy)) - corrected expected type
   template_rand_bytes,     // pseudorand_bytes (int (*)(unsigned char *buf, int num))
   template_rand_status     // status (int (*)(void))
};

/* --- Engine Control Commands --- */
static const ENGINE_CMD_DEFN template_cmd_defns[] = { // Renamed
    {1, "QKD_SERVICE_URL", "Sets the URL for the QKD service", ENGINE_CMD_FLAG_STRING },
    {0, NULL, NULL, 0}
};

// Renamed ctrl function
static int template_engine_ctrl(ENGINE *e, int cmd, long i, void *p, void (*f)(void)) {
    switch (cmd) {
    case 1: // QKD_SERVICE_URL
        if (!p) { fprintf(stderr, "Template Engine: NULL URL pointer\n"); return 0; }
        free(qkd_service_url); qkd_service_url = strdup((const char *)p);
        if (!qkd_service_url) { fprintf(stderr, "Template Engine: strdup failed\n"); return 0; }
        printf("Template Engine: Set service URL to %s\n", qkd_service_url);
        return 1;
    default: break;
    }
    return 0;
}

/* --- Engine Boilerplate --- */
// Renamed functions
static int template_engine_destroy(ENGINE *e) {
    printf("Template Engine: Destroying.\n");
    template_engine_close();
    free(qkd_service_url); qkd_service_url = NULL;
    return 1;
}
static int template_engine_init(ENGINE *e) {
    if (curl_global_init(CURL_GLOBAL_ALL)) { fprintf(stderr, "Template Engine: libcurl init failed\n"); return 0; }
    printf("Template Engine: Initializing.\n");
    return 1;
}
static int template_engine_finish(ENGINE *e) {
    printf("Template Engine: Finishing.\n");
    return 1;
}

/* --- Engine Binding --- */
static int bind_helper(ENGINE *e, const char *id) {
    // Use the template ID and name defined above
    if (!ENGINE_set_id(e, engine_template_id) ||
        !ENGINE_set_name(e, engine_template_name) ||
        !ENGINE_set_RAND(e, &template_rand_meth) ||      // Use template RAND method
        !ENGINE_set_ctrl_function(e, template_engine_ctrl) || // Use template ctrl func
        !ENGINE_set_cmd_defns(e, template_cmd_defns) ||      // Use template cmd defs
        !ENGINE_set_destroy_function(e, template_engine_destroy) ||
        !ENGINE_set_init_function(e, template_engine_init) ||
        !ENGINE_set_finish_function(e, template_engine_finish))
    {
        fprintf(stderr, "Template Engine: Failed to set engine properties.\n");
        return 0;
    }
    printf("Template Engine: bind_helper successful for ID %s\n", engine_template_id);
    return 1;
}

// For static linking (less common for engines)
#ifndef OPENSSL_NO_STATIC_ENGINE
// Renamed loading function if needed for static linking
void ENGINE_load_template(void) {
    ENGINE *e = ENGINE_new();
    if (!e) return;
    if (!bind_helper(e, engine_template_id)) { // Use template ID
        ENGINE_free(e); return;
    }
    ENGINE_add(e); ENGINE_free(e); ERR_clear_error();
}
#endif

// Standard dynamic engine loading entry point
IMPLEMENT_DYNAMIC_BIND_FN(bind_helper)
IMPLEMENT_DYNAMIC_CHECK_FN()