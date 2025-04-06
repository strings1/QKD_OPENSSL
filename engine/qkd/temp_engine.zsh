#!/bin/zsh

export PKG_CONFIG_PATH="/opt/homebrew/lib/pkgconfig:/opt/homebrew/Cellar/curl/8.13.0/lib/pkgconfig"

# Exit on first error
set -e
# Optional: uncomment below for very verbose script execution tracing
# set -x

# --- Configuration ---
SRC_FILE="template_engine.c"
DYLIB_NAME="libtemplate.dylib"
CONFIG_FILE="openssl_template.cnf"
ENGINE_ID="template"
QKD_URL="http://127.0.0.1:5000" # Example URL - CHANGE IF NEEDED

# --- Check for Dependencies ---
if ! command -v pkg-config &> /dev/null; then
    echo "Error: pkg-config not found. Please install it (brew install pkg-config)."
    exit 1
fi
# Check if pc files exist
if ! pkg-config --exists openssl libcurl; then # Add jansson if needed
    echo "Error: pkg-config cannot find openssl or libcurl .pc files."
    echo "Ensure OpenSSL and libcurl development packages are installed correctly (e.g., brew install openssl@3 curl)."
    exit 1
fi
# Add check for jansson if used:
# if ! pkg-config --exists jansson; then echo "Error: pkg-config cannot find jansson"; exit 1; fi


# --- Get Compiler Flags using pkg-config ---
OPENSSL_PC_NAME="openssl"
if ! pkg-config --exists ${OPENSSL_PC_NAME}; then
    OPENSSL_PC_NAME="openssl@3"
    if ! pkg-config --exists ${OPENSSL_PC_NAME}; then
       echo "Error: Cannot find pkg-config file for 'openssl' or 'openssl@3'."
       exit 1
    fi
fi
echo "Using pkg-config flags for: ${OPENSSL_PC_NAME}, libcurl" # Add , jansson if used

# Get CFLAGS (include paths etc)
CFLAGS=$(pkg-config --cflags ${OPENSSL_PC_NAME} libcurl) # Add jansson if used
# Get LIBS (library paths and names)
LIBS=$(pkg-config --libs ${OPENSSL_PC_NAME} libcurl)     # Add jansson if used


# --- Paths for Script ---
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
ENGINE_PATH="${SCRIPT_DIR}/${DYLIB_NAME}"
TEMP_CONFIG_PATH="${SCRIPT_DIR}/${CONFIG_FILE}"


# --- Step 1: Compilation ---
echo "Compiling ${SRC_FILE} into ${DYLIB_NAME}..."

# Get paths explicitly
OPENSSL_INCLUDE_DIR=$(pkg-config --variable=includedir openssl)
OPENSSL_LIBDIR=$(pkg-config --variable=libdir openssl)
CURL_CFLAGS=$(pkg-config --cflags libcurl)
CURL_LIBDIR=$(pkg-config --variable=libdir libcurl)

# Construct full path to Homebrew libcurl dylib (adjust filename if needed)
CURL_DYLIB_PATH="${CURL_LIBDIR}/libcurl.4.dylib"
if [[ ! -f "$CURL_DYLIB_PATH" ]]; then
    echo "Error: Homebrew libcurl dylib not found at $CURL_DYLIB_PATH"
    # Try common alternative name
     CURL_DYLIB_PATH="${CURL_LIBDIR}/libcurl.dylib"
     if [[ ! -f "$CURL_DYLIB_PATH" ]]; then
        echo "Error: Homebrew libcurl dylib not found at ${CURL_LIBDIR}/libcurl.dylib either."
        exit 1
     fi
fi
echo "Attempting to link directly against: ${CURL_DYLIB_PATH}"


# Get OpenSSL libs (-lssl -lcrypto etc) BUT NOT the -L path for it
OPENSSL_LIBS_ONLY=$(pkg-config --libs-only-l --libs-only-other openssl)

# Construct LDFLAGS for explicit lib paths and rpaths
# Only need OpenSSL LibDir here since Curl path is explicit
LDFLAGS="-L${OPENSSL_LIBDIR}"
LDFLAGS+=" -Wl,-rpath,${OPENSSL_LIBDIR} -Wl,-rpath,${CURL_LIBDIR}" # Still need rpath for Curl!

echo "Running gcc command linking full libcurl path:"
gcc -v -dynamiclib "${SCRIPT_DIR}/${SRC_FILE}" \
    -o "${ENGINE_PATH}" \
    ${=CFLAGS} \
    ${=LIBS} \
    -Wl,-install_name,@rpath/${DYLIB_NAME} \
    -Wl,-rpath,${SCRIPT_DIR}

# Check compilation result immediately
if [[ $? -ne 0 ]]; then
    echo "--------------------------------------------------"
    echo "ERROR: Compilation/Linking failed!"
    echo "--------------------------------------------------"
    exit 1
fi
echo "--------------------------------------------------"
echo "Compilation successful: ${ENGINE_PATH}"
echo "--------------------------------------------------"


# --- Step 2: Generate Temporary OpenSSL Config ---
echo "Generating temporary OpenSSL config: ${TEMP_CONFIG_PATH}..."
# (Config generation remains the same)
echo "openssl_conf = openssl_init

[openssl_init]
engines = engine_section

[engine_section]
${ENGINE_ID} = ${ENGINE_ID}_engine_config

[${ENGINE_ID}_engine_config]
engine_id = ${ENGINE_ID}
dynamic_path = ${ENGINE_PATH}
QKD_SERVICE_URL = \"${QKD_URL}\"
default_algorithms = RAND
init = 1
" > ${TEMP_CONFIG_PATH}
echo "Configuration generated."


# --- Step 3: Execute OpenSSL Command ---
echo "--------------------------------------------------"
echo "Running openssl rand with the engine..."
# Use the correct openssl binary path identified by pkg-config's prefix for safety
OPENSSL_BIN=$(pkg-config --variable=prefix ${OPENSSL_PC_NAME})/bin/openssl

# Set environment variables
OPENSSL_CONF=${TEMP_CONFIG_PATH} \
OPENSSL_MODULES=${SCRIPT_DIR} \
LD_LIBRARY_PATH=${SCRIPT_DIR} \
${OPENSSL_BIN} rand -engine ${ENGINE_ID} -hex 16

if [[ $? -ne 0 ]]; then
    echo "--------------------------------------------------"
    echo "ERROR: OpenSSL command failed!"
    # rm -f ${ENGINE_PATH} ${TEMP_CONFIG_PATH} # Optional cleanup on failure
    exit 1
fi
echo "OpenSSL command successful."
echo "--------------------------------------------------"


# --- Step 4: Cleanup ---
echo "Cleaning up..."
# rm -f ${ENGINE_PATH} ${TEMP_CONFIG_PATH}
echo "Cleanup complete."

exit 0