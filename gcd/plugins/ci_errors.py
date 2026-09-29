from collections.abc import Mapping
from dataclasses import dataclass, field

import requests

from gcd.core.models import ApprovalEntry, BasePlugin, ChangeIdentifier, TrackedChange

REQUIRED_CONFIG_KEYS = ["url", "api_key"]
TRIGGERING_APPROVAL_LABEL = "Verified"
STATUS_FIELD = "job_status"


@dataclass
class CiStatus:
    running: int = 0
    completed: int = 0
    unknown: int = 0
    comments: list[str] = field(default_factory=list)


class CiErrorsPlugin(BasePlugin):
    name = "ci_errors"
    version = "0.0.1"

    def _ask_for_errors(self, change_nr: int, patchset_nr: int) -> CiStatus | None:
        url = self.config.get("url")
        api_key = self.config.get("api_key")
        if not isinstance(url, str) or not url or not isinstance(api_key, str) or not api_key:
            self.log.error("_ask_for_errors: URL and API key must be nonempty strings")
            return None

        payload = {"changenumber": change_nr, "patchsetnr": patchset_nr}
        headers = {"ocp-apim-subscription-key": api_key, "content-type": "application/json"}

        try:
            res = requests.post(url, json=payload, headers=headers, timeout=10)
            res.raise_for_status()
            response: object = res.json()
        except requests.exceptions.Timeout:
            self.log.error(f"_ask_for_errors: request timed out for change {change_nr}")
            return None
        except requests.exceptions.HTTPError as error:
            status_code = error.response.status_code if error.response is not None else "unknown"
            self.log.error(f"_ask_for_errors: HTTP {status_code} for change {change_nr}")
            return None
        except requests.exceptions.RequestException as error:
            self.log.error(f"_ask_for_errors: request failed for change {change_nr}: {error}")
            return None
        except ValueError as error:
            self.log.error(f"_ask_for_errors: failed to parse response for change {change_nr}: {error}")
            return None

        statuses = CiStatus()
        if not isinstance(response, list):
            self.log.error(f"_ask_for_errors: response for change {change_nr} is not a list")
            return None

        for entry in response:
            if not isinstance(entry, Mapping):
                continue

            match entry.get(STATUS_FIELD, "unknown"):
                case "COMPLETED":
                    statuses.completed += 1
                    categories = entry.get("categories", [])
                    if not isinstance(categories, list):
                        continue

                    for category in categories:
                        if not isinstance(category, Mapping) or category.get("category") != "error":
                            continue

                        err_msg = self._comment_value(category.get("category"))
                        err_type = self._comment_value(category.get("err_type"))
                        job_link = self._comment_value(category.get("job_link"))
                        statuses.comments.append(f"({err_type}) {err_msg} - {job_link}")
                case "RUNNING":
                    statuses.running += 1
                case _:
                    statuses.unknown += 1
                    self.log.error(f"_ask_for_errors: unknown status for entry: {entry}")

        return statuses

    @staticmethod
    def _comment_value(value: object) -> str:
        return value if isinstance(value, str) else "<?>"

    def on_init(self) -> None:
        url = self.config.get("url")
        api_key = self.config.get("api_key")
        if isinstance(url, str) and url and isinstance(api_key, str) and api_key:
            self.log.info(f"on_init: plugin initialized with url={url}")
            return

        self.enabled = False
        self.log.error(
            f"on_init: init failed, required fields must be nonempty strings: {', '.join(REQUIRED_CONFIG_KEYS)}"
        )

    def _check_ci_errors(self, ch: TrackedChange) -> None:
        if not ch.current_patchset_number:
            self.log.error(f"_check_ci_errors: cannot determine current patchset number for {ch.id}")
            return

        statuses = self._ask_for_errors(ch.number, ch.current_patchset_number)
        if statuses is None:
            self.log.error(f"_check_ci_errors: failed to retrieve CI errors for {ch.id}")
            return

        msg = f"VERIFICATION: COMPLETED: {statuses.completed}, "
        msg += f"RUNNING: {statuses.running}, "
        msg += f"UNKNOWN: {statuses.unknown}"

        self.log.info(f"_check_ci_errors: {msg}")
        self.log.info(f"_check_ci_errors: errors: {len(statuses.comments)}")

        ch.comments.append(msg)
        ch.comments.extend(statuses.comments)
        ch.modified = True

    def on_exit(self) -> None:
        self.log.info("on_exit")

    def on_activate(self, change_id: ChangeIdentifier, change: TrackedChange) -> None:
        self.log.info(f"on_activate: {change_id}")
        self._check_ci_errors(change)

    def on_new_approval(self, change_id: ChangeIdentifier, new_approval: ApprovalEntry) -> None:
        if new_approval.label != TRIGGERING_APPROVAL_LABEL:
            return

        self.log.info(f"on_new_approval {change_id}, new approvals: {new_approval}")
        ch = self.ctx.changes.by_id(change_id)
        if ch is None:
            self.log.error(f"on_new_approval: cannot retrieve change by id {change_id}")
            return

        self._check_ci_errors(ch)


plugin_class = CiErrorsPlugin
