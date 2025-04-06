#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <openssl/engine.h>
#include <openssl/crypto.h>
#include <openssl/evp.h>
#include <openssl/err.h>

// Include for BIO
#include <openssl/bio.h>
#include <openssl/ssl.h>
// Include for JSON parsing (if you choose to use a library like jansson)
// #include <jansson.h>

// Include for libcurl
#include <curl/curl.h>

// Define the engine ID
static const char *engine_remote_qkd_id = "remote_qkd";
// Define the engine name
static const char *engine_remote_qkd_name = "Remote QKD Key Engine";

// Define custom control command numbers
#define REMOTE_QKD_CMD_SET_ALICE_URL 1
#define REMOTE_QKD_CMD_SET_BOB_URL   2
#define REMOTE_QKD_CMD_OPEN_SESSION  3 // Not used in the python test, but good to have.
#define REMOTE_QKD_CMD_CLOSE_SESSION 4 // Not used in the python test, but good to have.

// Static variables to store Alice and Bob URLs.  These need to be accessible
// to the key loading functions.
static char *alice_url = NULL;
static char *bob_url   = NULL;
static int    key_handle = -1; //store key_handle

// Function Prototypes
static int  engine_remote_qkd_init(ENGINE *e);
static int  engine_remote_qkd_finish(ENGINE *e);
static int  engine_remote_qkd_destroy(ENGINE *e);
static int  engine_remote_qkd_ctrl(ENGINE *e, int cmd, long i, void *p, void (*f)(void));
static EVP_PKEY *engine_remote_qkd_load_privkey(ENGINE *e, const char *key_id, UI_METHOD *ui, void *data);
static EVP_PKEY *engine_remote_qkd_load_pubkey(ENGINE *e, const char *key_id, UI_METHOD *ui, void *data);

// Utility function to make HTTP requests using libcurl
//  Added error checking and simplified
static char *http_request(const char *url, const char *post_data) {
    CURL *curl;
    CURLcode res;
    char *response_data = NULL;
    long response_code = 0;

    curl_global_init(CURL_GLOBAL_DEFAULT);
    curl = curl_easy_init();
    if (!curl) {
        fprintf(stderr, "curl_easy_init failed\n");
        return NULL;
    }

    curl_easy_setopt(curl, CURLOPT_URL, url);
    if (post_data) {
        curl_easy_setopt(curl, CURLOPT_POST, 1L);
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, post_data);
    }
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, &write_callback); //set write call back
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response_data);     //set write data
    curl_easy_setopt(curl, CURLOPT_FAILONERROR, 1L);  // Fail on HTTP errors

    res = curl_easy_perform(curl);
    if (res != CURLE_OK) {
        fprintf(stderr, "curl_easy_perform failed: %s\n", curl_easy_strerror(res));
        curl_easy_cleanup(curl);
        curl_global_cleanup();
        return NULL;
    }

    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &response_code);
    if (response_code != 200) {
        fprintf(stderr, "HTTP error: %ld\n", response_code);
        if(response_data) free(response_data);
        curl_easy_cleanup(curl);
        curl_global_cleanup();
        return NULL;
    }
    curl_easy_cleanup(curl);
    curl_global_cleanup();
    return response_data;
}

// Callback function to handle the response from the HTTP request.
//  This function is called by libcurl as it receives data.
size_t write_callback(char *data, size_t size, size_t nmemb, void *userp) {
    size_t total_size = size * nmemb;
    char **buffer = (char **)userp;

    if (*buffer == NULL) {
        *buffer = (char *)malloc(total_size + 1);
    } else {
        *buffer = (char *)realloc(*buffer, strlen(*buffer) + total_size + 1);
    }
    if (*buffer == NULL) {
        fprintf(stderr, "Memory allocation failed\n");
        return 0; // Signal an error to curl
    }
    memcpy(*buffer + strlen(*buffer), data, total_size);
    (*buffer)[strlen(*buffer) + total_size] = '\0'; // Null-terminate
    return total_size;
}

// Function to parse JSON and extract the key.  Uses a simple approach.
//  For production, use a proper JSON library.
static char *parse_key_from_json(const char *json_response) {
    const char *key_start = strstr(json_response, "\"key_buffer\": \"");
    if (!key_start) return NULL;

    key_start += strlen("\"key_buffer\": \"");
    const char *key_end = strchr(key_start, '"');
    if (!key_end) return NULL;

    size_t key_len = key_end - key_start;
    char *key = (char *)malloc(key_len + 1);
    if (!key) return NULL;

    memcpy(key, key_start, key_len);
    key[key_len] = '\0';
    return key;
}

// Function to parse JSON and extract the key_handle.
static int parse_key_handle_from_json(const char *json_response) {
    const char *handle_start = strstr(json_response, "\"key_handle\":");
    if (!handle_start) return -1;  // Return -1 to indicate an error

    handle_start += strlen("\"key_handle\":");
    // Skip spaces
    while (*handle_start == ' ') handle_start++;

    char *endptr;
    long handle = strtol(handle_start, &endptr, 10);
    if (endptr == handle_start || (*endptr != '\0' && *endptr != '}')) {
        return -1; // Conversion error or invalid character
    }
    return (int)handle;
}

// Engine initialization function
static int engine_remote_qkd_init(ENGINE *e) {
    if (!ENGINE_set_id(e, engine_remote_qkd_id)) {
        fprintf(stderr, "ENGINE_set_id failed\n");
        return 0;
    }
    if (!ENGINE_set_name(e, engine_remote_qkd_name)) {
        fprintf(stderr, "ENGINE_set_name failed\n");
        return 0;
    }

    // Initialize any data structures or connections here if needed.
    // For this example, we don't have any specific initialization.
    return 1;
}

// Engine cleanup function
static int engine_remote_qkd_finish(ENGINE *e) {
    // Clean up any resources allocated during the engine's operation.
    // For this example, we free the URL strings.
    if (alice_url) {
        free(alice_url);
        alice_url = NULL;
    }
    if (bob_url) {
        free(bob_url);
        bob_url = NULL;
    }
    key_handle = -1;

    return 1;
}

// Engine destruction function
static int engine_remote_qkd_destroy(ENGINE *e) {
    //  ENGINE_free is handled by openssl
    return 1;
}

// Engine control function to handle custom commands
static int engine_remote_qkd_ctrl(ENGINE *e, int cmd, long i, void *p, void (*f)(void)) {
    int ret = 0;
    switch (cmd) {
        case REMOTE_QKD_CMD_SET_ALICE_URL:
            if (p) {
                alice_url = strdup((char *)p); //copy the string
                if (!alice_url) {
                    fprintf(stderr, "strdup failed for alice_url\n");
                    return 0;
                }
                ret = 1;
            }
            break;
        case REMOTE_QKD_CMD_SET_BOB_URL:
            if (p) {
                bob_url = strdup((char *)p);  //copy the string
                 if (!bob_url) {
                    fprintf(stderr, "strdup failed for bob_url\n");
                    return 0;
                }
                ret = 1;
            }
            break;
        case REMOTE_QKD_CMD_OPEN_SESSION:  //Added OPEN SESSION
             {
                char *response = http_request(alice_url, "{}"); // Empty JSON for open
                if (response)
                {
                    key_handle = parse_key_handle_from_json(response);
                    if(key_handle != -1)
                    {
                         ret = 1;
                    }
                    else
                    {
                         fprintf(stderr, "OPEN SESSION: Could not parse key_handle\n");
                         ret = 0;
                    }
                    free(response);
                }
                else
                {
                    fprintf(stderr, "OPEN SESSION: http_request failed\n");
                    ret = 0;
                }
                break;
             }
        case REMOTE_QKD_CMD_CLOSE_SESSION: //Added CLOSE SESSION
            {
                char close_url_alice[256];
                char close_url_bob[256];
                snprintf(close_url_alice, sizeof(close_url_alice), "%s/qkd_close", alice_url);
                snprintf(close_url_bob, sizeof(close_url_bob), "%s/qkd_close", bob_url);

                char *response_alice = http_request(close_url_alice, "{}");
                char *response_bob = http_request(close_url_bob, "{}");
                if(response_alice) free(response_alice);
                if(response_bob) free(response_bob);
                key_handle = -1;
                ret = 1;
                break;
            }
        default:
            fprintf(stderr, "Unknown control command: %d\n", cmd);
            break;
    }
    return ret;
}

// Function to load a private key
static EVP_PKEY *engine_remote_qkd_load_privkey(ENGINE *e, const char *key_id, UI_METHOD *ui, void *data) {
    char *response = NULL;
    char get_key_url[256];

    if (!alice_url || key_handle == -1) {
        fprintf(stderr, "Alice URL not set or key_handle invalid\n");
        ERR_raise(ERR_LIB_ENGINE, ENGINE_R_UNINITIALIZED);
        return NULL;
    }
    snprintf(get_key_url, sizeof(get_key_url), "%s/qkd_get_key", alice_url);
    char post_data[64];  //increased size
    snprintf(post_data, sizeof(post_data), "{\"key_handle\": %d}", key_handle);

    response = http_request(get_key_url, post_data);
    if (!response) {
        fprintf(stderr, "Failed to get private key from %s\n", alice_url);
        ERR_raise(ERR_LIB_ENGINE, ENGINE_R_FAILED_LOAD_PRIVATE_KEY);
        return NULL;
    }

    char *private_key_pem = parse_key_from_json(response);
    free(response);
    if (!private_key_pem) {
        fprintf(stderr, "Failed to parse private key from JSON\n");
        ERR_raise(ERR_LIB_ENGINE, ENGINE_R_FAILED_LOAD_PRIVATE_KEY);
        return NULL;
    }

    // Convert PEM string to EVP_PKEY
    EVP_PKEY *pkey = NULL;
    BIO *mem_bio = BIO_new_mem_buf(private_key_pem, -1); // -1: auto calculate length
    if (!mem_bio) {
        fprintf(stderr, "BIO_new_mem_buf failed\n");
        free(private_key_pem);
        ERR_raise(ERR_LIB_ENGINE, ERR_R_BIO_LIB);
        return NULL;
    }

    // Assuming the key is RSA, change if it's a different type
    pkey = PEM_read_bio_PrivateKey(mem_bio, NULL, NULL, NULL);
    BIO_free(mem_bio);
    free(private_key_pem);

    if (!pkey) {
        fprintf(stderr, "PEM_read_bio_PrivateKey failed\n");
        ERR_raise(ERR_LIB_ENGINE, ENGINE_R_ASN1_LIB);
        return NULL;
    }
    return pkey;
}

// Function to load a public key
static EVP_PKEY *engine_remote_qkd_load_pubkey(ENGINE *e, const char *key_id, UI_METHOD *ui, void *data) {
    char *response = NULL;
    char get_key_url[256];

    if (!bob_url || key_handle == -1) {
        fprintf(stderr, "Bob URL not set or key_handle invalid\n");
        ERR_raise(ERR_LIB_ENGINE, ENGINE_R_UNINITIALIZED);
        return NULL;
    }

    snprintf(get_key_url, sizeof(get_key_url), "%s/qkd_get_key", bob_url);
     char post_data[64];  //increased size
    snprintf(post_data, sizeof(post_data), "{\"key_handle\": %d}", key_handle);

    response = http_request(get_key_url, post_data);
    if (!response) {
        fprintf(stderr, "Failed to get public key from %s\n", bob_url);
        ERR_raise(ERR_LIB_ENGINE, ENGINE_R_FAILED_LOAD_PUBLIC_KEY);
        return NULL;
    }

    char *public_key_pem = parse_key_from_json(response);
    free(response);
    if (!public_key_pem) {
        fprintf(stderr, "Failed to parse public key from JSON\n");
        ERR_raise(ERR_LIB_ENGINE, ENGINE_R_FAILED_LOAD_PUBLIC_KEY);
        return NULL;
    }

    // Convert PEM string to EVP_PKEY
    EVP_PKEY *pkey = NULL;
    BIO *mem_bio = BIO_new_mem_buf(public_key_pem, -1);
    if (!mem_bio) {
        fprintf(stderr, "BIO_new_mem_buf failed\n");
        free(public_key_pem);
        ERR_raise(ERR_LIB_ENGINE, ERR_R_BIO_LIB);
        return NULL;
    }
    // Assuming the key is RSA, change if it's a different type
    pkey = PEM_read_bio_PUBKEY(mem_bio, NULL, NULL, NULL);
    BIO_free(mem_bio);
    free(public_key_pem);

    if (!pkey) {
        fprintf(stderr, "PEM_read_bio_PUBKEY failed\n");
        ERR_raise(ERR_LIB_ENGINE, ENGINE_R_ASN1_LIB);
        return NULL;
    }
    return pkey;
}

// Engine setup function
static int engine_remote_qkd(ENGINE *e) {
    if (!ENGINE_set_id(e, engine_remote_qkd_id) ||
        !ENGINE_set_name(e, engine_remote_qkd_name) ||
        !ENGINE_set_init_function(e, engine_remote_qkd_init) ||
        !ENGINE_set_finish_function(e, engine_remote_qkd_finish) ||
        !ENGINE_set_destroy_function(e, engine_remote_qkd_destroy) || //set destroy
        !ENGINE_set_ctrl_function(e, engine_remote_qkd_ctrl) ||
        !ENGINE_set_load_privkey_function(e, engine_remote_qkd_load_privkey) ||
        !ENGINE_set_load_pubkey_function(e, engine_remote_qkd_load_pubkey)) {
        fprintf(stderr, "Failed to set engine functions\n");
        return 0;
    }

     // Define and set up the custom control commands
    ENGINE_CMD_DEFN cmds[] = {
        {REMOTE_QKD_CMD_SET_ALICE_URL, "SET_ALICE_URL", "Set the URL for Alice", ENGINE_CMD_FLAG_STRING},
        {REMOTE_QKD_CMD_SET_BOB_URL,   "SET_BOB_URL",   "Set the URL for Bob",   ENGINE_CMD_FLAG_STRING},
        {REMOTE_QKD_CMD_OPEN_SESSION,  "OPEN_SESSION",  "Open QKD session",      ENGINE_CMD_FLAG_NO_INPUT}, // Added
        {REMOTE_QKD_CMD_CLOSE_SESSION, "CLOSE_SESSION", "Close QKD session",     ENGINE_CMD_FLAG_NO_INPUT}, // Added
        {0, NULL, NULL, 0}
    };

    if (!ENGINE_set_ctrl_commands(e, cmds)) {
        fprintf(stderr, "ENGINE_set_ctrl_commands failed\n");
        return 0;
    }
    return 1;
}

// OpenSSL Engine entry point
extern "C" {
    ENGINE_EXPORT int engine_load_remote_qkd(void) {
        ENGINE *e = ENGINE_new();
        if (!e) {
            fprintf(stderr, "ENGINE_new failed\n");
            return 0;
        }
        if (!engine_remote_qkd(e)) {
            ENGINE_free(e);
            fprintf(stderr, "engine_remote_qkd failed\n");
            return 0;
        }
        ENGINE_add(e);
        // The engine will be freed by OpenSSL's internal mechanisms.
        return 1;
    }
}

