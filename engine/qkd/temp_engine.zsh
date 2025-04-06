#!/bin/zsh


# Generate OpenSSL config
ENGINE_PATH="$(pwd)/template.dylib"
CONFIG_FILE="$(pwd)/openssl.cnf"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_FILE="template_engine.c"
DYLIB_NAME="libtemplate.dylib"
gcc -v -dynamiclib "${SCRIPT_DIR}/${SRC_FILE}" \
    -o "${ENGINE_PATH}" \
    ${=CFLAGS} \
    ${=LIBS} \
    -Wl,-install_name,@rpath/${DYLIB_NAME} \
    -Wl,-rpath,${SCRIPT_DIR}

cat << EOF > $CONFIG_FILE
openssl_conf = openssl_init

[openssl_init]
engines = engine_section

[engine_section]
template = template_engine

[template_engine]
engine_id = template
dynamic_path = $ENGINE_PATH
init = 1
EOF

# Execute with engine parameters (replace URL with your QKD service)
OPENSSL_CONF=$CONFIG_FILE \
OPENSSL_MODULES=$(dirname $ENGINE_PATH) \
openssl rand -engine "template -QKD_SERVICE_URL http://your-qkd-service.example.com" -hex 100