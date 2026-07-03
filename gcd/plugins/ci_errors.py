import requests

from gcd.core.models import ApprovalEntry, BasePlugin, ChangeIdentifier, TrackedChange

REQUIRED_CONFIG_KEYS = ["url", "api_key"]
TRIGGERING_APPROVAL_LABEL = "Verified"
STATUS_FIELD = "job_status"


class CiErrorsPlugin(BasePlugin):
    name = "ci_errors"
    version = "0.0.1"

    def _ask_for_errors(self, change_nr: str, patchset_nr: int) -> dict[str, int | list] | None:
        url = self.config.get("url")
        api_key = self.config.get("api_key")

        payload = {"changenumber": int(change_nr), "patchsetnr": patchset_nr}
        headers = {"ocp-apim-subscription-key": api_key, "content-type": "application/json"}

        try:
            res = requests.post(url, json=payload, headers=headers, timeout=10)
            res.raise_for_status()
            response = res.json()
        except requests.exceptions.Timeout:
            self.log.error(f"_ask_for_errors: request timed out for change {change_nr}")
            return None
        except requests.exceptions.HTTPError as e:
            self.log.error(f"_ask_for_errors: HTTP {e.response.status_code} for change {change_nr}")
            return None
        except requests.exceptions.RequestException as e:
            self.log.error(f"_ask_for_errors: request failed for change {change_nr}: {e}")
            return None
        except ValueError as e:
            self.log.error(f"_ask_for_errors: failed to parse response for change {change_nr}: {e}")
            return None

        statuses = {"running": 0, "completed": 0, "unknown": 0, "comments": []}

        for en in response:
            match en.get(STATUS_FIELD, "unknown"):
                case "COMPLETED":
                    statuses["completed"] += 1

                    for cat in en.get("categories", []):
                        if cat.get("category") == "error":
                            err_msg = cat.get("category", "<?>")
                            err_type = cat.get("err_type", "<?>")
                            job_link = cat.get("job_link", "<?>")

                            statuses["comments"].append(f"({err_type}) {err_msg} - {job_link}")

                case "RUNNING":
                    statuses["running"] += 1

                case _:
                    statuses["unknown"] += 1
                    self.log(f"_ask_for_errors: ERROR: unknown status for entry: {en}")

        return statuses

    def on_init(self):
        if all(key in self.config for key in REQUIRED_CONFIG_KEYS):
            self.log.info(
                f"on_init: plugin initialized with url={self.config['url']} and key='{self.config['api_key'][:3]}...' "
            )
        else:
            self.enabled = False
            self.log.error(
                "on_init: init failed, one or more of required fields are not configured:"
                f" {', '.join(REQUIRED_CONFIG_KEYS)}"
            )

    def _check_ci_errors(self, ch: TrackedChange) -> None:
        if not ch.current_patchset_number:
            self.log.error(f"_check_ci_errors: cannot determine current patchset number for {ch.id}")
            return

        statuses = self._ask_for_errors(ch.number, ch.current_patchset_number)

        if statuses is None:
            self.log.error(f"_check_ci_errors: failed to retrieve CI errors for {ch.id}")
            return

        msg = f"VERIFICATION: COMPLETED: {statuses['completed']}, "
        msg += f"RUNNING: {statuses['running']}, "
        msg += f"UNKNOWN: {statuses['unknown']}"

        self.log.info(f"_check_ci_errors: {msg}")
        self.log.info(f"_check_ci_errors: errors: {len(statuses['comments'])}")

        ch.comments.append(msg)
        ch.comments.extend(statuses["comments"])
        ch.modified = True

    def on_exit(self) -> None:
        self.log.info("on_exit")

    def on_activate(self, change_id: ChangeIdentifier, ch: TrackedChange) -> None:
        self.log.info(f"on_activate: {change_id}")
        self._check_ci_errors(ch)

    def on_new_approval(self, change_id: ChangeIdentifier, new_approval: ApprovalEntry) -> None:
        if new_approval.label == TRIGGERING_APPROVAL_LABEL:
            self.log.info(f"on_new_approval {change_id}, new approvals: {new_approval}")

            if not (ch := self.ctx.changes.by_id(change_id)):
                self.log.error(f"on_new_approval: cannot retrieve change by id {change_id}")
                return

                self._check_ci_errors(ch)


plugin_class = CiErrorsPlugin
