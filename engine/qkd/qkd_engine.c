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
#include <jansson.h>

/* --- Engine Identification --- */
static const char *engine_qkd_id = "qkd_engine";
static const char *engine_qkd_name = "QKD API Engine for OpenSSL RNG";

/* --- Configuration & State --- */
// NOTE: Using static globals is simpler for an example but NOT thread-safe
// without mutexes. Proper implementation should use ENGINE_set_ex_data.
static char *qkd_service_url = NULL; // e.g., "http://192.168.1.233:5000"
static char *qkd_key_handle = NULL;
static unsigned char *qkd_key_buffer = NULL;
static size_t qkd_key_buffer_len = 0;
static size_t qkd_key_buffer_pos = 0;
// static pthread_mutex_t qkd_lock = PTHREAD_MUTEX_INITIALIZER; // Add if threading needed

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
        /* out of memory! */
        fprintf(stderr, "QKD Engine: not enough memory (realloc returned NULL)\n");
        return 0;
    }

    mem->memory = ptr;
    memcpy(&(mem->memory[mem->size]), contents, realsize);
    mem->size += realsize;
    mem->memory[mem->size] = 0;

    return realsize;
}

/* --- Helper: Perform HTTP POST --- */
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
        fprintf(stderr, "QKD Engine: curl_easy_init() failed\n");
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
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "qkd-openssl-engine/1.0");
    // Add error buffer for more details
    // char errorBuffer[CURL_ERROR_SIZE];
    // curl_easy_setopt(curl, CURLOPT_ERRORBUFFER, errorBuffer);

    res = curl_easy_perform(curl);

    if (res != CURLE_OK) {
        fprintf(stderr, "QKD Engine: curl_easy_perform() failed: %s\n", curl_easy_strerror(res));
        // fprintf(stderr, "Curl error detail: %s\n", errorBuffer);
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
         fprintf(stderr, "QKD Engine: HTTP request failed with code %ld. Response: %s\n", http_code, chunk.memory ? chunk.memory : "N/A");
         free(chunk.memory);
         return NULL;
    }

    // Minimal JSON parsing (replace with Jansson for robustness)
    // WARNING: Very basic parsing, assumes simple {"key": "value"} format
    if (chunk.memory) {
        response_body = chunk.memory; // Keep the response
        if (handle_out) {
            char *p = strstr(response_body, "\"key_handle\"");
            if (p) {
                p = strchr(p + 12, '"'); // Find opening quote of value
                if (p) {
                    p++;
                    char *q = strchr(p, '"'); // Find closing quote
                    if (q) {
                        size_t len = q - p;
                        *handle_out = malloc(len + 1);
                        if(*handle_out) {
                            strncpy(*handle_out, p, len);
                            (*handle_out)[len] = '\0';
                        }
                    }
                }
            }
            if (!*handle_out) fprintf(stderr, "QKD Engine: Failed to parse 'key_handle' from response: %s\n", response_body);

        } else if (key_out && key_len_out) {
             char *p = strstr(response_body, "\"key_buffer\"");
             if (p) {
                p = strchr(p + 12, '"'); // Find opening quote of value
                if (p) {
                    p++;
                    char *q = strchr(p, '"'); // Find closing quote
                    if (q) {
                        size_t base64_len = q - p;
                        // Allocate max possible decoded size
                        *key_out = malloc(base64_len); // Base64 decoded is smaller
                        if (*key_out) {
                           // Use OpenSSL's Base64 decoder
                           // Need to copy the base64 part first, as EVP_DecodeBlock might read past 'q' if not null terminated there
                           char* base64_str = strndup(p, base64_len);
                           if (base64_str) {
                               *key_len_out = EVP_DecodeBlock(*key_out, (const unsigned char*)base64_str, base64_len);
                               free(base64_str);
                               if ((int)*key_len_out < 0) { // EVP_DecodeBlock returns -1 on error
                                   fprintf(stderr, "QKD Engine: Base64 decoding failed.\n");
                                   free(*key_out);
                                   *key_out = NULL;
                                   *key_len_out = 0;
                               }
                           } else {
                               fprintf(stderr, "QKD Engine: Failed to extract base64 string.\n");
                                free(*key_out);
                                *key_out = NULL;
                                *key_len_out = 0;
                           }
                        }
                    }
                }
             }
            if (!*key_out) fprintf(stderr, "QKD Engine: Failed to parse 'key_buffer' from response: %s\n", response_body);
        }
    } else {
         fprintf(stderr, "QKD Engine: No response body received.\n");
         return NULL;
    }

    // Caller must free response_body if they don't need it after parsing
    return response_body;
}


/* --- QKD API Interaction Functions --- */

// Returns 0 on success, -1 on error
static int qkd_engine_connect() {
    if (!qkd_service_url) {
        fprintf(stderr, "QKD Engine: Service URL not set.\n");
        // OPENSSL_PUT_ERROR(ENGINE, QKD_ENG_R_URL_NOT_SET); // Add custom errors
        return -1;
    }

    // Step 1: Open
    char *open_url = NULL;
    char *open_response = NULL;
    if (asprintf(&open_url, "%s/qkd_open", qkd_service_url) < 0) return -1;
    printf("QKD Engine: Opening connection via %s...\n", open_url);
    open_response = perform_post(open_url, "{}", &qkd_key_handle, NULL, NULL);
    free(open_url);

    if (!open_response || !qkd_key_handle) {
        fprintf(stderr, "QKD Engine: Failed to open QKD connection.\n");
        free(open_response); // Free response body if perform_post succeeded but handle parsing failed
        return -1;
    }
    printf("QKD Engine: Got Key Handle: %s\n", qkd_key_handle);
    free(open_response); // Don't need the full response anymore

    // Step 2: Connect Blocking (Only need to call our local service)
    char *connect_url = NULL;
    char *connect_payload = NULL;
    char *connect_response = NULL;
    if (asprintf(&connect_url, "%s/qkd_connect_blocking", qkd_service_url) < 0) goto connect_err;
    if (asprintf(&connect_payload, "{\"key_handle\": \"%s\"}", qkd_key_handle) < 0) goto connect_err;

    printf("QKD Engine: Connecting blocking via %s...\n", connect_url);
    connect_response = perform_post(connect_url, connect_payload, NULL, NULL, NULL);
    free(connect_url);
    free(connect_payload);
    connect_url = NULL; connect_payload = NULL; // prevent double free in cleanup

    if (!connect_response) {
        fprintf(stderr, "QKD Engine: Failed to connect blocking.\n");
        goto connect_err;
    }
    printf("QKD Engine: Connect blocking successful.\n");
    free(connect_response);

    return 0; // Success

connect_err:
    fprintf(stderr, "QKD Engine: Error during connect blocking phase.\n");
    free(connect_url);
    free(connect_payload);
    free(connect_response);
    if (qkd_key_handle) {
        // Attempt to close if we got a handle but failed to connect
        char *close_url = NULL;
        char *close_payload = NULL;
         if (asprintf(&close_url, "%s/qkd_close", qkd_service_url) >= 0 &&
             asprintf(&close_payload, "{\"key_handle\": \"%s\"}", qkd_key_handle) >= 0) {
            printf("QKD Engine: Attempting cleanup close...\n");
            char *close_resp = perform_post(close_url, close_payload, NULL, NULL, NULL);
            free(close_resp); // Ignore result during cleanup
         }
         free(close_url);
         free(close_payload);

        free(qkd_key_handle);
        qkd_key_handle = NULL;
    }
    return -1;
}

// Fetches a new key, returns 0 on success, -1 on error
static int qkd_engine_fetch_key() {
    if (!qkd_service_url || !qkd_key_handle) {
        fprintf(stderr, "QKD Engine: Not connected (no URL or key handle).\n");
        return -1;
    }

    // Clear old buffer if exists
    free(qkd_key_buffer);
    qkd_key_buffer = NULL;
    qkd_key_buffer_len = 0;
    qkd_key_buffer_pos = 0;

    char *get_key_url = NULL;
    char *get_key_payload = NULL;
    char *get_key_response = NULL;

    if (asprintf(&get_key_url, "%s/qkd_get_key", qkd_service_url) < 0) return -1;
    if (asprintf(&get_key_payload, "{\"key_handle\": \"%s\"}", qkd_key_handle) < 0) {
        free(get_key_url);
        return -1;
    }

    printf("QKD Engine: Fetching key via %s...\n", get_key_url);
    get_key_response = perform_post(get_key_url, get_key_payload, NULL, &qkd_key_buffer, &qkd_key_buffer_len);

    free(get_key_url);
    free(get_key_payload);

    if (!get_key_response || !qkd_key_buffer || qkd_key_buffer_len == 0) {
        fprintf(stderr, "QKD Engine: Failed to get key or key is empty.\n");
        free(get_key_response); // Free response if needed
        free(qkd_key_buffer);   // Free buffer if allocated but parsing failed
        qkd_key_buffer = NULL;
        qkd_key_buffer_len = 0;
        return -1;
    }
    printf("QKD Engine: Successfully fetched %zu bytes of key material.\n", qkd_key_buffer_len);
    free(get_key_response); // Don't need response body anymore
    qkd_key_buffer_pos = 0; // Start reading from beginning
    return 0;
}

// Closes connection
static void qkd_engine_close() {
    if (qkd_key_handle && qkd_service_url) {
        char *close_url = NULL;
        char *close_payload = NULL;
        if (asprintf(&close_url, "%s/qkd_close", qkd_service_url) >= 0 &&
            asprintf(&close_payload, "{\"key_handle\": \"%s\"}", qkd_key_handle) >= 0)
        {
            printf("QKD Engine: Closing connection (handle: %s)...\n", qkd_key_handle);
            char *close_resp = perform_post(close_url, close_payload, NULL, NULL, NULL);
            // We don't strictly need to check the response on close
            free(close_resp);
        }
        free(close_url);
        free(close_payload);

        free(qkd_key_handle);
        qkd_key_handle = NULL;
    }
     // Free remaining buffer
    free(qkd_key_buffer);
    qkd_key_buffer = NULL;
    qkd_key_buffer_len = 0;
    qkd_key_buffer_pos = 0;

    // Don't free qkd_service_url here, it's set via control command
}


/* --- RAND_METHOD Implementation --- */

static int qkd_rand_init(ENGINE *e) {
    // Could connect here, or connect lazily on first bytes request
    printf("QKD Engine: RAND_METHOD init.\n");
    return 1;
}

static int qkd_rand_bytes(unsigned char *buf, int num) {
    // Add mutex lock here if thread-safety is needed
    // pthread_mutex_lock(&qkd_lock);

    int bytes_provided = 0;
    if (!qkd_key_handle) {
        printf("QKD Engine: First call to rand_bytes, attempting connection...\n");
        if (qkd_engine_connect() != 0) {
             fprintf(stderr, "QKD Engine: Connection failed during rand_bytes.\n");
             // pthread_mutex_unlock(&qkd_lock);
             return 0; // Indicate failure
        }
    }

    while (bytes_provided < num) {
        // Check if we need more key material from API
        if (qkd_key_buffer_pos >= qkd_key_buffer_len) {
            printf("QKD Engine: Key buffer empty or exhausted, fetching new key...\n");
            if (qkd_engine_fetch_key() != 0) {
                fprintf(stderr, "QKD Engine: Failed to fetch new key during rand_bytes.\n");
                // Only return failure if we couldn't provide *any* bytes
                // pthread_mutex_unlock(&qkd_lock);
                return (bytes_provided > 0); // Return 1 if we provided *some* bytes before failure
            }
            // If fetch succeeded but got 0 bytes (shouldn't happen based on check in fetch_key)
             if (qkd_key_buffer_len == 0) {
                fprintf(stderr, "QKD Engine: Fetched key but got 0 bytes.\n");
                 // pthread_mutex_unlock(&qkd_lock);
                return (bytes_provided > 0);
             }
        }

        // How many bytes can we copy from the current buffer?
        size_t bytes_to_copy = qkd_key_buffer_len - qkd_key_buffer_pos;
        int bytes_needed = num - bytes_provided;

        if (bytes_to_copy > bytes_needed) {
            bytes_to_copy = bytes_needed;
        }

        // Copy the bytes
        memcpy(buf + bytes_provided, qkd_key_buffer + qkd_key_buffer_pos, bytes_to_copy);
        qkd_key_buffer_pos += bytes_to_copy;
        bytes_provided += bytes_to_copy;
    }

    // printf("QKD Engine: Provided %d random bytes.\n", bytes_provided);
    // Add mutex unlock here
    // pthread_mutex_unlock(&qkd_lock);
    return 1; // Indicate success
}

static int qkd_rand_cleanup(ENGINE *e) {
    printf("QKD Engine: RAND_METHOD cleanup. Closing connection.\n");
    // Add mutex lock/unlock if used
    qkd_engine_close();
    // Free URL if it was dynamically allocated by engine itself (not the case here)
    return 1;
}

// We don't add external entropy, we *are* the source
static int qkd_rand_add(ENGINE *e, const void *buf, int num, double entropy) {
    return 1; // No-op, always success
}
static int qkd_rand_seed(ENGINE *e, const void *buf, int num) {
     return 1; // No-op, always success
}

// Status: 1 if we think we are okay (have URL), 0 otherwise.
// More sophisticated check possible (e.g., try a quick status ping to API?)
static int qkd_rand_status(ENGINE *e) {
     // Add mutex lock/unlock if used
     // For basic check: return 1 if URL is set and maybe if handle exists?
    int status = (qkd_service_url != NULL);
     // Could potentially add: && (qkd_key_handle != NULL || qkd_engine_connect() == 0)
     // But connecting in status might be too slow.
     // pthread_mutex_unlock(&qkd_lock);
    return status;
}


// Define the RAND_METHOD structure
static RAND_METHOD qkd_rand_meth = {
    qkd_rand_seed,      // seed
    qkd_rand_bytes,     // bytes
    qkd_rand_cleanup,   // cleanup
    qkd_rand_add,       // add
    qkd_rand_bytes,     // pseudorand_bytes (use same as bytes)
    qkd_rand_status     // status
};

/* --- Engine Control Commands --- */
static const ENGINE_CMD_DEFN qkd_cmd_defns[] = {
    {
        // Command number (0 is reserved)
        1,
        // Command name (used in config file)
        "QKD_SERVICE_URL",
        // Command description
        "Sets the URL for the QKD Key Manager service",
        // Flags (usually ENGINE_CMD_FLAG_STRING for string input)
        ENGINE_CMD_FLAG_STRING
    },
    // Add more commands if needed (e.g., setting timeouts)
    {0, NULL, NULL, 0} // Terminator
};

static int qkd_engine_ctrl(ENGINE *e, int cmd, long i, void *p, void (*f)(void)) {
    switch (cmd) {
    case 1: // Corresponds to QKD_SERVICE_URL command number
        if (p == NULL) {
            fprintf(stderr, "QKD Engine: Invalid NULL pointer for QKD_SERVICE_URL\n");
            // Add OpenSSL error
            return 0;
        }
        // Free existing URL if set previously
        free(qkd_service_url);
        qkd_service_url = strdup((const char *)p);
        if (!qkd_service_url) {
             fprintf(stderr, "QKD Engine: Failed to allocate memory for URL\n");
             return 0;
        }
        printf("QKD Engine: Set service URL to %s\n", qkd_service_url);
        return 1;
    default:
        break;
    }
    return 0; // Command not found
}

/* --- Engine Boilerplate --- */

static int qkd_engine_destroy(ENGINE *e) {
    printf("QKD Engine: Destroying.\n");
    // Free resources
    qkd_engine_close(); // Ensure closed even if RAND cleanup wasn't called
    free(qkd_service_url);
    qkd_service_url = NULL;
    // Free RAND_METHOD if it was dynamically allocated (not the case here)
    // Destroy mutex if used
    // CRYPTO_free_ex_data(CRYPTO_EX_INDEX_ENGINE, e, &ex_data_handle); // If using ex_data
    return 1;
}

static int qkd_engine_init(ENGINE *e) {
    // Initialize libcurl globally (safe to call multiple times)
    if (curl_global_init(CURL_GLOBAL_ALL)) {
         fprintf(stderr, "QKD Engine: Failed to initialize libcurl\n");
         return 0;
    }
    // Init mutex if needed
    printf("QKD Engine: Initializing.\n");
    // Any other init tasks?
    return 1;
}

static int qkd_engine_finish(ENGINE *e) {
    printf("QKD Engine: Finishing.\n");
    // Cleanup libcurl? Maybe not here if other parts of app use it.
    // curl_global_cleanup(); // Usually called once at very end of application life
    // Cleanup mutex if needed
    return 1;
}


/* --- Engine Binding --- */
// This function is called by OpenSSL when the engine is loaded.
// It binds the implementations provided by the engine.
static int bind_helper(ENGINE *e, const char *id) {
    if (!ENGINE_set_id(e, engine_qkd_id) ||
        !ENGINE_set_name(e, engine_qkd_name) ||
        !ENGINE_set_RAND(e, &qkd_rand_meth) || // Register our RAND method
        !ENGINE_set_ctrl_function(e, qkd_engine_ctrl) ||
        !ENGINE_set_cmd_defns(e, qkd_cmd_defns) ||
        !ENGINE_set_destroy_function(e, qkd_engine_destroy) ||
        !ENGINE_set_init_function(e, qkd_engine_init) ||
        !ENGINE_set_finish_function(e, qkd_engine_finish))
    {
        fprintf(stderr, "QKD Engine: Failed to set engine properties.\n");
        return 0;
    }
    printf("QKD Engine: bind_helper successful for ID %s\n", engine_qkd_id);
    return 1;
}

// For static linking (less common for engines)
#ifndef OPENSSL_NO_STATIC_ENGINE
void ENGINE_load_qkd(void) {
    ENGINE *e = ENGINE_new();
    if (!e) return;
    if (!bind_helper(e, engine_qkd_id)) {
        ENGINE_free(e);
        return;
    }
    ENGINE_add(e);
    ENGINE_free(e); // Decrease ref count from ENGINE_new
    ERR_clear_error();
}
#endif

// Standard dynamic engine loading entry point
IMPLEMENT_DYNAMIC_BIND_FN(bind_helper)
IMPLEMENT_DYNAMIC_CHECK_FN()