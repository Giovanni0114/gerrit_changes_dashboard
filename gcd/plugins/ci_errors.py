import requests

from gcd.core.models import ApprovalEntry, BasePlugin, ChangeIdentifier

REQUIRED_CONFIG_KEYS = ["url", "api_key"]
TRIGGERING_APPROVAL_LABEL = "Verified"
STATUS_FIELD = "job_status"


class CiErrorsPlugin(BasePlugin):
    name = "ci_errors"
    version = "0.0.1"

    def _ask_for_errors(self, change_nr: str, patchset_nr: int) -> dict[str, int] | None:
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

        statuses: dict[str, int] = {}

        for en in response:
            status = en.get(STATUS_FIELD, "<undefined>")

            if status in statuses:
                statuses[status] += 1
            else:
                statuses[status] = 1

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

    def on_exit(self) -> None:
        self.log.info("on_exit")

    def on_activate(self) -> None:
        self.log.info("on_activate")

    def on_new_approval(self, change_id: ChangeIdentifier, new_approval: ApprovalEntry) -> None:
        if new_approval.label == TRIGGERING_APPROVAL_LABEL:
            self.log.info(f"on_new_approval {change_id}, new approvals: {new_approval}")

            if not (ch := self.ctx.changes.by_id(change_id)):
                self.log.error(f"on_new_approval: cannot retrieve change by id {change_id}")
                return

            if not ch.current_patchset_number:
                self.log.error(f"on_new_approval: cannot determine current patchset number for {change_id}")
                return

            statuses = self._ask_for_errors(change_id.number, ch.current_patchset_number)

            if statuses is None:
                self.log.error(f"on_new_approval: failed to retrieve CI errors for {change_id}")
                return

            ch.comments.append(f"VERIFICATION JOB STATUS: {statuses}")
            ch.modified = True


plugin_class = CiErrorsPlugin
