from __future__ import annotations

# Import submodules so ex.history, ex.config etc. are accessible (needed for test patches)
from . import history, config, core, utils, watch, code_tools, explainers, setup_tools, _paths, _constants, output, patterns

# Re-export paths for backward compat
from ._paths import HISTORY_FILE, CONFIG_FILE

# Re-export all public symbols for "import errex as ex; ex.func()" compatibility
from .config import load_config, manage_config, load_profile, list_profiles, delete_profile
from .history import (save_history, show_history, show_recent, find_similar, clear_history,
                      export_history, show_stats, interactive_history, rate_last, add_note,
                      find_by_name, list_named, export_csv, search_history, dedup_history,
                      show_last, pin_entry)
from .core import (call_claude, explain_error, compare_errors, chat_loop, ask_about_last, retry_last, run_bulk)
from .code_tools import (lint_file, explain_code, generate_test, explain_diff, explain_inline,
                         grep_and_explain, summarize_log)
from .explainers import (explain_exit_code, explain_http, explain_cron, explain_sql,
                         explain_env_var, explain_yaml, explain_dockerfile, explain_regex,
                         _cron_local)
from .setup_tools import (run_setup, run_doctor, install_shell, scan_logs, detect_environment,
                          print_completion, run_command, rerun_last_command, open_last_in_browser)
from .utils import (read_file, get_error_input, extract_error_type, _parse_since, format_json_error,
                    extract_snippet, redact_secrets, notify, check_for_update, get_env_info,
                    share_explanation, post_webhook, _detect_yaml_type, _error_fingerprint,
                    search_github_issues)
from .output import show_token_usage, show_perf, copy_to_clipboard
from .watch import watch_file
from ._constants import (SYSTEM_PROMPT, API_TIMEOUT, CONFIG_DEFAULTS, CONFIG_TYPES, EXIT_CODES,
                          HTTP_CODES, ENV_VARS, ERROR_PATTERNS)
from .patterns import match_pattern, list_patterns
from .cli import main
