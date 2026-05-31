import anyio
import httpx

from app.main import app


def test_health_endpoint() -> None:
    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get("/api/v1/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    anyio.run(run)


def test_static_frontend_entrypoints_are_served() -> None:
    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            root = await client.get("/")
            login = await client.get("/pages/login.html")
            styles = await client.get("/assets/css/styles.css")

        assert root.status_code == 200
        assert login.status_code == 200
        assert styles.status_code == 200

    anyio.run(run)
