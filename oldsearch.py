#!/usr/bin/env python3
# Прокси-поисковик для старых браузеров (Windows 95 - 2000).
# Запускается на современном компьютере: python oldsearch.py
# Старый компьютер открывает http://<адрес-этого-компьютера>:8080/ по обычному HTTP.
# Сервер сам ходит на HTTPS-сайты, а старому браузеру отдаёт простой HTML (без скриптов, кодировка windows-1251).
import html, json, re, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, unquote_to_bytes, urljoin, urlparse
from urllib.request import Request, urlopen

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
PER = 10
UA = "Mozilla/5.0 (compatible; OldSearchProxy/1.0)"
NAMES = ["Википедия (рус)", "Wikipedia (eng)", "Викисловарь (рус)", "Google Books (книги)",
         "Internet Archive", "GitHub (проекты)", "iTunes (музыка)", "DuckDuckGo (кратко)"]


def fetch(url):
    with urlopen(Request(url, headers={"User-Agent": UA}), timeout=15) as r:
        return r.read(3000000), r.headers.get_content_charset(), r.headers.get_content_type()


def getjson(url):
    return json.loads(fetch(url)[0].decode("utf-8", "replace"))


def strip(s):
    return html.unescape(re.sub(r"<[^>]+>", "", str(s or "")))


def wiki(host):
    def f(q, p):
        d = getjson("https://%s/w/api.php?action=query&list=search&format=json&srlimit=%d&sroffset=%d&srsearch=%s"
                    % (host, PER, (p - 1) * PER, quote(q)))
        return [(x["title"], "https://%s/wiki/%s" % (host, quote(x["title"].replace(" ", "_"))), strip(x["snippet"]))
                for x in d["query"]["search"]], True
    return f


def books(q, p):
    d = getjson("https://www.googleapis.com/books/v1/volumes?maxResults=%d&startIndex=%d&q=%s" % (PER, (p - 1) * PER, quote(q)))
    out = []
    for x in d.get("items", []):
        v = x.get("volumeInfo", {})
        out.append((v.get("title", "?"), v.get("infoLink", "https://books.google.com/"),
                    ", ".join(v.get("authors", [])) + ". " + v.get("description", "")))
    return out, True


def archive(q, p):
    d = getjson("https://archive.org/advancedsearch.php?q=%s&fl%%5B%%5D=identifier&fl%%5B%%5D=title&fl%%5B%%5D=description&rows=%d&page=%d&output=json"
                % (quote(q), PER, p))
    return [(x.get("title", x["identifier"]), "https://archive.org/details/" + x["identifier"], strip(x.get("description", "")))
            for x in d["response"]["docs"]], True


def github(q, p):
    d = getjson("https://api.github.com/search/repositories?per_page=%d&page=%d&q=%s" % (PER, p, quote(q)))
    return [(x["full_name"], x["html_url"], x.get("description") or "") for x in d["items"]], True


def itunes(q, p):
    d = getjson("https://itunes.apple.com/search?limit=20&term=" + quote(q))
    out = []
    for x in d["results"]:
        t = x.get("trackName") or x.get("collectionName") or x.get("artistName") or "?"
        u = x.get("trackViewUrl") or x.get("collectionViewUrl") or x.get("artistLinkUrl") or "https://music.apple.com/"
        out.append((t, u, x.get("artistName", "")))
    return out, False


def ddg(q, p):
    d = getjson("https://api.duckduckgo.com/?format=json&no_html=1&skip_disambig=1&q=" + quote(q))
    out = []
    if d.get("AbstractText"):
        out.append((d.get("Heading", q), d.get("AbstractURL", ""), d["AbstractText"]))
    for r in d.get("RelatedTopics", []):
        for s in r.get("Topics", [r]):
            if s.get("FirstURL"):
                out.append((s["Text"], s["FirstURL"], ""))
    return out, False


FUNCS = [wiki("ru.wikipedia.org"), wiki("en.wikipedia.org"), wiki("ru.wiktionary.org"), books, archive, github, itunes, ddg]


def e(s):
    return html.escape(str(s))


def layout(body):
    return ('<HTML><HEAD><META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=windows-1251">'
            '<TITLE>Googol</TITLE></HEAD><BODY BGCOLOR="#FFFFFF" TEXT="#000000" LINK="#0000CC" VLINK="#551A8B">'
            + body + '</BODY></HTML>')


LOGO = ('<FONT FACE="Arial" SIZE="%d"><B><FONT COLOR="#3366CC">G</FONT><FONT COLOR="#CC0000">o</FONT>'
        '<FONT COLOR="#FFAA00">o</FONT><FONT COLOR="#3366CC">g</FONT><FONT COLOR="#009900">o</FONT>'
        '<FONT COLOR="#CC0000">l</FONT></B></FONT>')


def form(q="", src=0):
    opts = "".join('<OPTION VALUE="%d"%s>%s</OPTION>' % (i, " SELECTED" if i == src else "", e(n)) for i, n in enumerate(NAMES))
    return ('<FORM METHOD="GET" ACTION="/search"><INPUT TYPE="text" NAME="q" SIZE="45" VALUE="%s"><BR><BR>'
            '<FONT FACE="Arial" SIZE="2">Искать в:</FONT> <SELECT NAME="src">%s</SELECT> '
            '<INPUT TYPE="submit" VALUE="Поиск"></FORM>' % (e(q), opts))


def home():
    return layout('<BR><CENTER>' + LOGO % 7 + '<BR><BR>' + form() + '</CENTER>')


def results(q, src, p):
    head = '<TABLE WIDTH="100%%"><TR><TD WIDTH="1%%">%s</TD><TD>%s</TD></TR></TABLE><HR SIZE="1">' % (LOGO % 5, form(q, src))
    try:
        items, paged = FUNCS[src](q, p)
    except Exception as ex:
        return layout(head + '<FONT FACE="Arial" SIZE="3" COLOR="#CC0000">Ошибка: %s</FONT>' % e(ex))
    if not items:
        return layout(head + '<FONT FACE="Arial" SIZE="3">Ничего не найдено.</FONT>')
    b = head
    for t, u, d in items:
        b += ('<FONT FACE="Arial" SIZE="4"><A HREF="/page?u=%s">%s</A></FONT><BR>'
              '<FONT FACE="Arial" SIZE="2" COLOR="#006600">%s</FONT><BR>'
              '<FONT FACE="Arial" SIZE="2">%s</FONT><BR><BR>') % (quote(u, safe=""), e(t), e(u[:80]), e(d[:250]))
    if paged:
        base = "/search?q=%s&src=%d&p=" % (quote(q), src)
        b += '<HR SIZE="1"><FONT FACE="Arial" SIZE="2">'
        if p > 1:
            b += '<A HREF="%s%d">&lt; Назад</A> &nbsp; ' % (base, p - 1)
        if len(items) >= PER:
            b += '<A HREF="%s%d">Дальше &gt;</A>' % (base, p + 1)
        b += '</FONT>'
    return layout(b)


def proxify(src, base):
    src = re.sub(r"(?is)<(script|style|iframe|object|embed|noscript|svg)\b.*?</\1>", "", src)
    src = re.sub(r"(?is)<(img|link|meta|source|input type=.hidden.)\b[^>]*>", "", src)

    def rep(m):
        raw = html.unescape(m.group(2))
        if raw.startswith("#") or raw.lower().startswith(("javascript:", "mailto:")):
            return m.group(0)
        return 'href="/page?u=%s"' % quote(urljoin(base, raw), safe="")
    return re.sub(r'(?i)\bhref\s*=\s*(["\'])(.*?)\1', rep, src)


def page(u):
    bar = '<FONT FACE="Arial" SIZE="2"><A HREF="/">Googol</A> | %s</FONT><HR SIZE="1">' % e(u[:90])
    try:
        if urlparse(u).scheme not in ("http", "https"):
            raise ValueError("неверный адрес")
        data, cs, ct = fetch(u)
        if ct not in ("text/html", "application/xhtml+xml", "text/plain"):
            raise ValueError("этот тип файла (%s) не показывается" % ct)
        text = data.decode(cs or "utf-8", "replace")
        if ct == "text/plain":
            text = "<PRE>%s</PRE>" % e(text)
        return layout(bar + proxify(text, u))
    except Exception as ex:
        return layout(bar + '<FONT FACE="Arial" SIZE="3" COLOR="#CC0000">Ошибка: %s</FONT>' % e(ex))


def parse_qs(qs):
    out = {}
    for part in qs.split("&"):
        k, _, v = part.partition("=")
        raw = unquote_to_bytes(v.replace("+", " "))
        try:
            out[k] = raw.decode("utf-8")
        except UnicodeDecodeError:
            out[k] = raw.decode("cp1251", "replace")   # старые браузеры шлют windows-1251
    return out


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        path, _, qs = self.path.partition("?")
        a = parse_qs(qs)
        q = a.get("q", "").strip()
        try:
            src = max(0, min(len(FUNCS) - 1, int(a.get("src", 0))))
            p = max(1, int(a.get("p", 1)))
        except ValueError:
            src, p = 0, 1
        if path == "/api":   # JSONP для страницы search.html
            cb = re.sub(r"[^\w.]", "", a.get("callback", "cb")) or "cb"
            try:
                items, paged = FUNCS[src](q, p)
                res = {"items": [list(i) for i in items], "more": bool(paged and len(items) >= PER)}
            except Exception as ex:
                res = {"error": str(ex)}
            data = ("%s(%s);" % (cb, json.dumps(res))).encode("ascii")
            ctype = "application/javascript"
        else:
            if path == "/search" and q:
                body = results(q, src, p)
            elif path == "/page" and a.get("u"):
                body = page(a["u"])
            else:
                body = home()
            data = body.encode("cp1251", "xmlcharrefreplace")
            ctype = "text/html; charset=windows-1251"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Googol работает: http://<IP-этого-компьютера>:%d/  (Ctrl+C - выход)" % PORT)
    print("Открывайте только в домашней сети: сервер не защищён.")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
