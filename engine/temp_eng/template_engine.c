#include <openssl/engine.h>
#include <openssl/rand.h>
#include <stdio.h>
#include <string.h>
#include <curl/curl.h>

#define ENGINE_ID "template"
#define ENGINE_NAME "Quantum Engine"

// Mandatory RAND methods
static int template_rand_status(void) { return 1; }
static int template_rand_seed(const void *buf, int num) { return 1; }
static int template_rand_add(const void *buf, int num, double entropy) { return 1; }

static int template_rand_bytes(unsigned char *buf, int num) {
    printf("=== QKD RAND ACTIVE ===\n");
    memset(buf, 0xAB, num); // 0xAA = 170 = 'aa' in hex
    return 1;
}

static RAND_METHOD template_rand_method = {
    template_rand_seed,
    template_rand_bytes,
    NULL, // cleanup
    template_rand_add,
    template_rand_bytes, // pseudorand
    template_rand_status
};

// Engine initialization with priority override
static int template_init(ENGINE *e) {
    ENGINE_set_RAND(e, &template_rand_method);
    RAND_set_rand_method(&template_rand_method); // Force override
    return 1;
}

static int bind_helper(ENGINE *e, const char *id) {
    return ENGINE_set_id(e, ENGINE_ID) &&
           ENGINE_set_name(e, ENGINE_NAME) &&
           ENGINE_set_init_function(e, template_init) &&
           ENGINE_set_flags(e, ENGINE_FLAGS_NO_REGISTER_ALL) && // Prevent conflicts
           ENGINE_set_RAND(e, &template_rand_method);
}

IMPLEMENT_DYNAMIC_CHECK_FN()
IMPLEMENT_DYNAMIC_BIND_FN(bind_helper)