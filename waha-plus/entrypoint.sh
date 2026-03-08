#!/bin/sh


#
# Calculate UV_THREADPOOL_SIZE based on number of CPUs
#
# Try to get CPU count using Node.js, fallback to 1 if it fails
cpus=$(node -e "const os = require('os'); console.log(os.cpus().length);" 2>/dev/null) || cpus=1
# Make sure cpus is a number, default to 1 if not
case $cpus in
  ''|*[!0-9]*) cpus=1 ;;
esac
uv_threadpool_size=$(($cpus * 2))

# Check if uv_threadpool_size is less than 4 (default), set it to 4 if it is
if [ "$uv_threadpool_size" -lt 4 ]; then
  uv_threadpool_size=4
fi

# Set UV_THREADPOOL_SIZE as an environment variable
export UV_THREADPOOL_SIZE="${UV_THREADPOOL_SIZE:-$uv_threadpool_size}"

#
# Handle API key hashing
#
# Save WHATSAPP_API_KEY or WAHA_API_KEY in a variable (WHATSAPP_API_KEY has priority)
if [ -n "$WHATSAPP_API_KEY" ]; then
  key="$WHATSAPP_API_KEY"
elif [ -n "$WAHA_API_KEY" ]; then
  key="$WAHA_API_KEY"
fi

# Unset both environment variables
unset WHATSAPP_API_KEY
unset WAHA_API_KEY

# Process the key if it exists
if [ -n "$key" ]; then
  # Check if key is already hashed
  if echo "$key" | grep -q "^sha512:"; then
    # If already hashed, use it as is
    export WAHA_API_KEY="$key"
  else
    # Hash the key using sha512sum
    HASHED_KEY=$(echo -n "$key" | sha512sum | awk '{print $1}')
    export WAHA_API_KEY="sha512:$HASHED_KEY"
  fi
fi

#
# Start your application using node with exec to ensure proper signal handling
#
exec node dist/main
