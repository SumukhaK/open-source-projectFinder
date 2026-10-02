import secrets
import time
from email.utils import parsedate_to_datetime

import httpx
from app.core.config import Settings


class ProviderError(Exception):
    pass


class GitHubProvider:
    def __init__(
        self,
        client_id,
        secret,
        callback,
        transport=None,
        sleep=time.sleep,
        settings=None,
    ):
        self.client_id, self.secret, self.callback = client_id, secret, callback
        self.transport, self.sleep = transport, sleep
        self.settings = settings or Settings(_env_file=None)

    def exchange(self, code, verifier):
        # A timeout may occur after GitHub consumes the code. Restart login instead of replaying it.
        try:
            with httpx.Client(
                transport=self.transport,
                timeout=self.settings.github_timeout,
                follow_redirects=False,
            ) as client:
                response = client.post(
                    "https://github.com/login/oauth/access_token",
                    headers={"Accept": "application/json"},
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.secret,
                        "code": code,
                        "redirect_uri": self.callback,
                        "code_verifier": verifier,
                    },
                )
                response.raise_for_status()
                data = response.json()
                if (
                    not isinstance(data, dict)
                    or not isinstance(data.get("access_token"), str)
                    or not data["access_token"]
                    or data.get("error")
                ):
                    raise ProviderError()
                return data
        except (httpx.HTTPError, ValueError) as error:
            raise ProviderError() from error

    def user(self, token):
        with httpx.Client(
            transport=self.transport,
            timeout=self.settings.github_timeout,
            follow_redirects=False,
        ) as client:
            for attempt in range(self.settings.github_attempts):
                response = None
                try:
                    response = client.get(
                        "https://api.github.com/user",
                        headers={
                            "Authorization": "Bearer " + token,
                            "Accept": "application/vnd.github+json",
                            "X-GitHub-Api-Version": "2022-11-28",
                        },
                    )
                    if response.status_code == 200:
                        data = response.json()
                        if (
                            not isinstance(data, dict)
                            or type(data.get("id")) is not int
                            or not isinstance(data.get("login"), str)
                        ):
                            raise ProviderError()
                        return data
                    retryable = response.status_code in (429, 500, 502, 503, 504) or (
                        response.status_code == 403
                        and (
                            "Retry-After" in response.headers
                            or response.headers.get("X-RateLimit-Remaining") == "0"
                        )
                    )
                    if not retryable:
                        raise ProviderError()
                except (httpx.TimeoutException, httpx.NetworkError):
                    pass
                except (ValueError, httpx.HTTPError) as error:
                    raise ProviderError() from error
                if attempt == self.settings.github_attempts - 1:
                    raise ProviderError()
                delay = (
                    self.settings.retry_base_delay * (2**attempt)
                    + secrets.randbelow(1001) / 1000 * self.settings.retry_jitter
                )
                if response is not None:
                    retry_after = response.headers.get("Retry-After")
                    reset = (
                        response.headers.get("X-RateLimit-Reset")
                        if response.headers.get("X-RateLimit-Remaining") == "0"
                        else None
                    )
                    if (
                        response.status_code in (403, 429)
                        and not retry_after
                        and not reset
                    ):
                        # GitHub requires at least a minute without usable rate-limit headers.
                        raise ProviderError()
                    try:
                        if retry_after:
                            try:
                                requested = float(retry_after)
                            except ValueError:
                                requested = (
                                    parsedate_to_datetime(retry_after).timestamp()
                                    - time.time()
                                )
                            delay = max(delay, requested)
                        if reset:
                            delay = max(delay, float(reset) - time.time())
                    except (ValueError, TypeError, OverflowError):
                        raise ProviderError()
                if delay > self.settings.retry_max_delay:
                    raise ProviderError()
                self.sleep(delay)
        raise ProviderError()
