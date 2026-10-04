/* Protect an in-memory SDK credential from same-UID child processes. */
#include <node_api.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <signal.h>
static napi_value lock(napi_env env, napi_callback_info info) {
  struct rlimit limit = {0, 0};
  if (setrlimit(RLIMIT_CORE, &limit) || prctl(PR_SET_DUMPABLE, 0, 0, 0, 0)) {
    napi_throw_error(env, NULL, "process credential protection failed"); return NULL;
  }
  signal(SIGUSR1, SIG_IGN); /* Do not permit a child to activate Node inspector. */
  napi_value out; napi_get_undefined(env, &out); return out;
}
static napi_value init(napi_env env, napi_value exports) {
  napi_value fn; napi_create_function(env, "lock", NAPI_AUTO_LENGTH, lock, NULL, &fn);
  napi_set_named_property(env, exports, "lock", fn); return exports;
}
NAPI_MODULE(NODE_GYP_MODULE_NAME, init)
