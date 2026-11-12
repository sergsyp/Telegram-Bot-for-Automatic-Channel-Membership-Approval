from __future__ import annotations

import base64
from dataclasses import dataclass
from urllib.parse import quote

import aiohttp


class GitHubError(RuntimeError):
    pass


class GitHubAuthorizationError(GitHubError):
    """Token rejected or lacking access; do not include the token in errors."""


@dataclass
class GitHubContentsClient:
    token: str
    repository: str
    archive_branch: str
    base_branch: str

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _json(self, method: str, url: str, expected: set[int], **kwargs):
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.request(method, url, **kwargs) as response:
                payload = await response.json(content_type=None)
                if response.status not in expected:
                    if response.status == 401 or (response.status == 403 and
                        response.headers.get("X-RateLimit-Remaining") != "0" and
                        not response.headers.get("Retry-After") and
                        "rate limit" not in str(payload.get("message", "")).lower()):
                        raise GitHubAuthorizationError(f"GitHub authorization failed: HTTP {response.status}")
                    raise GitHubError(f"GitHub API returned {response.status}: {payload.get('message', 'unknown error')}")
                return payload, response.status

    async def ensure_branch(self) -> None:
        base = f"https://api.github.com/repos/{self.repository}"
        _, status = await self._json(
            "GET", f"{base}/git/ref/heads/{quote(self.archive_branch, safe='')}", {200, 404}
        )
        if status == 200:
            return
        ref, _ = await self._json("GET", f"{base}/git/ref/heads/{quote(self.base_branch, safe='')}", {200})
        await self._json(
            "POST",
            f"{base}/git/refs",
            {201},
            json={"ref": f"refs/heads/{self.archive_branch}", "sha": ref["object"]["sha"]},
        )

    async def put_file(self, path: str, content: str) -> None:
        base = f"https://api.github.com/repos/{self.repository}/contents/{quote(path, safe='/')}"
        current, status = await self._json(
            "GET", base, {200, 404}, params={"ref": self.archive_branch}
        )
        body = {
            "message": f"Архивировать Telegram: {path}",
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": self.archive_branch,
        }
        if status == 200:
            body["sha"] = current["sha"]
        await self._json("PUT", base, {200, 201}, json=body)
