"""Checklist de produção: SEO, legal, 404 e consentimento."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_robots_txt(client: TestClient):
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert "text/plain" in r.headers.get("content-type", "")
    assert "Disallow: /admin" in r.text
    assert "Sitemap:" in r.text
    assert "/sitemap.xml" in r.text


def test_sitemap_xml(client: TestClient):
    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    assert "xml" in r.headers.get("content-type", "")
    assert "<urlset" in r.text
    for path in ("/", "/grid", "/privacidade", "/termos", "/hall-lendas"):
        assert path in r.text
    assert "/admin" not in r.text


def test_404_html(client: TestClient):
    r = client.get("/pagina-que-nao-existe-xyz", follow_redirects=False)
    assert r.status_code == 404
    assert "text/html" in r.headers.get("content-type", "")
    assert "não encontrada" in r.text.casefold() or "nao encontrada" in r.text.casefold()
    assert 'href="/"' in r.text


def test_404_json_quando_accept_json(client: TestClient):
    r = client.get("/pagina-que-nao-existe-xyz", headers={"Accept": "application/json"}, follow_redirects=False)
    assert r.status_code == 404
    assert r.json()["detail"]


def test_privacidade_e_termos(client: TestClient):
    for path in ("/privacidade", "/termos"):
        r = client.get(path)
        assert r.status_code == 200
        assert "THDFM" in r.text or "Técnicos Horríveis" in r.text


def test_footer_links_legais_e_banner_cookies(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    assert 'href="/privacidade"' in r.text
    assert 'href="/termos"' in r.text
    assert "cookie-banner" in r.text
    assert "cookie-consent.js" in r.text
    # AdSense só após consentimento (meta + loader, sem script direto)
    assert "thdfm-adsense-client" in r.text
    assert "pagead2.googlesyndication.com/pagead/js/adsbygoogle.js" not in r.text


def test_og_image_padrao_no_base(client: TestClient):
    r = client.get("/")
    assert 'property="og:image"' in r.text
    assert "og-default.png" in r.text
