"""HTMX helper endpoints for empty placeholder elements."""

from litestar import Controller, get


class ElementController(Controller):
    """Controller for htmx elements."""

    path = "/elements"
    tags = ["elements"]

    @get(path="empty/{tag:str}/{_id:str}", summary="Get an empty element.")
    async def empty(self, tag: str, _id: str) -> str:
        """Get an empty element."""
        return f'<{tag} id="{_id}"></{tag}>'
