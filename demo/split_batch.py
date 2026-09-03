import json, sys, re, os

def slugify(url):
    return re.sub(r'[^a-zA-Z0-9]+', '_', url)[:120]

def main():
    infile = sys.argv[1]
    outdir = sys.argv[2]
    with open(infile, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    # find the line that starts with '[{"url"'
    data_line = None
    for line in lines:
        if line.strip().startswith('[{"url"'):
            data_line = line
            break
    if data_line is None:
        print("No data line found")
        return
    data = json.loads(data_line)
    os.makedirs(outdir, exist_ok=True)
    index = []
    for item in data:
        url = item.get('url')
        content = item.get('content', '')
        fname = slugify(url) + '.md'
        path = os.path.join(outdir, fname)
        with open(path, 'w', encoding='utf-8') as out:
            out.write(content)
        index.append({'url': url, 'file': fname, 'len': len(content)})
    print(json.dumps(index, indent=2))

if __name__ == '__main__':
    main()
