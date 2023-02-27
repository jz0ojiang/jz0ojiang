import httpx
import re
import pathlib

root = pathlib.Path(__file__).parent.resolve()

def get_latest_posts() -> list:
    r = httpx.get("https://blog.im0o.top/api/getLatest5Posts")
    lines = []
    for i in r.json()['data']:
        # print(f"- [{i['title']}]({i['_link']})")
        lines.append(f"- [{i['title']}]({i['_link']}) - {i['date'].split('T')[0]}")
        if i['description'] == "文章描述":
            continue
        i["description"] = i["description"].replace("<br/>", " ").replace("<br>", " ").replace("<br />", " ")
        if len(i['description']) > 50:
            i['description'] = i['description'][:50] + "..."
        # print(f"  `{i['description']}`")
        lines.append(f"  *{i['description']}*")
    return lines

def replace_chunk(content, marker, chunk, inline=False):
    r = re.compile(
        r"<!\-\- {} starts \-\->.*<!\-\- {} ends \-\->".format(marker, marker),
        re.DOTALL,
    )
    if not inline:
        chunk = "\n{}\n".format(chunk)
    chunk = "<!-- {} starts -->{}<!-- {} ends -->".format(marker, chunk, marker)
    return r.sub(chunk, content)

if __name__ == "__main__":
    readme = root / "README.md"
    readme_contents = readme.open(encoding='utf-8').read()
    latest_posts = "\n\n".join(get_latest_posts())
    
    rewritten = replace_chunk(readme_contents, "latest_posts", latest_posts)
    # print(rewritten)
    readme.open("w", encoding='utf-8').write(rewritten)