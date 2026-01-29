import io
import re
import requests
import json
from flask import Flask, request, jsonify, send_file, Response

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # ensure jsonify emits real Unicode (e.g. "Götzen-Dämmerung")

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
GUTENDEX_API_URL = "https://gutendex.com/books"

# Priority mapping: The first mime type in the list is the one we use for download
FORMAT_MAPPING = {
    'epub': ['application/epub+zip'],
    'mobi': ['application/x-mobipocket-ebook', 'application/kindle'],
    'pdf': ['application/pdf'],
    'html': ['text/html'],
    'txt': ['text/plain', 'text/plain; charset=utf-8']
}

# ---------------------------------------------------------
# HELPER: PARSER
# ---------------------------------------------------------
def parse_search_query(raw_query):
    """
    Parses 'author=smith format=pdf' into API params.
    """
    params = {}
    search_terms = []
    
    # We default to showing common formats if the user doesn't ask for one
    target_formats = ['epub', 'mobi'] 

    pattern = r'(\w+)=(.+?)(?=\s+\w+=|$)'
    matches = list(re.finditer(pattern, raw_query))

    # Fallback for simple queries like "Metamorphosis"
    if not matches:
        return {"search": raw_query}, target_formats

    for match in matches:
        key = match.group(1).lower()
        value = match.group(2).strip()
        
        if key in ['title', 'author', 'search']:
            search_terms.append(value)
        elif key in ['lang', 'language']:
            params['languages'] = value[:2]
        elif key == 'format':
            # 1. Tell Gutendex to ONLY return books with this format
            if value.lower() in FORMAT_MAPPING:
                params['mime_type'] = FORMAT_MAPPING[value.lower()][0]
                # 2. Tell our display logic to only show this format button
                target_formats = [value.lower()]

    if search_terms:
        params['search'] = " ".join(search_terms)

    return params, target_formats

# ---------------------------------------------------------
# HELPER: FILENAME FORMATTER
# ---------------------------------------------------------
def format_filename(book_data, fmt_type):
    """
    Creates filename: 'Surname - Title [lang].ext'
    Keeps special characters (UTF-8) but removes illegal filesystem chars.
    """
    # 1. Extract Surname (First author, text before comma)
    if book_data.get('authors'):
        full_name = book_data['authors'][0]['name'] # "Nietzsche, Friedrich Wilhelm"
        surname = full_name.split(',')[0].strip()   # "Nietzsche"
    else:
        surname = "Unknown"

    # 2. Extract Title (Cleanup newlines or excessive length)
    title = book_data['title'].replace('\r', '').replace('\n', ' ')
    # Limit title length to ~42 chars to avoid filesystem errors
    if len(title) > 42:
        title = title[:42].strip() + "..."

    # 3. Extract Language
    langs = book_data.get('languages', ['en'])
    lang_code = langs[0] if langs else 'en'

    # 4. Construct base string
    filename = f"{surname} - {title} [{lang_code}].{fmt_type}"

    # 5. Sanitize for Filesystem (keep accents, remove / \ : * ? " < > |)
    # We replace illegal chars with standard hyphens or empty strings
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    
    return filename


# ---------------------------------------------------------
# ENDPOINT 1: SEARCH
# ---------------------------------------------------------
@app.route('/search', methods=['GET'])
def search_books():
    raw_query = request.args.get('q', '')
    if not raw_query:
        return Response(json.dumps({"error": "Missing 'q'"}, ensure_ascii=False),
                        mimetype='application/json; charset=utf-8',
                        status=400)

    api_params, target_formats = parse_search_query(raw_query)
    
    try:
        # Fast: Gutendex does the filtering now
        response = requests.get(GUTENDEX_API_URL, params=api_params)
        data = response.json()
        
        results = []
        # We can increase the limit now that we removed the slow size check
        for book in data.get('results', [])[:5]: 
            
            available_options = []
            
            # Check which of the target formats exist for this specific book
            for fmt_key in target_formats:
                if fmt_key not in FORMAT_MAPPING: continue
                
                # Check if the book has any of the mime types for this format
                has_format = any(mime in book['formats'] for mime in FORMAT_MAPPING[fmt_key])
                
                if has_format:
                    available_options.append({
                        "type": fmt_key,
                        "download_link": f"/download/{book['id']}/{fmt_key}"
                    })

            # Only return books that actually have the format user asked for
            if available_options:
                results.append({
                    "id": book['id'],
                    "title": book['title'],
                    "authors": ", ".join([a['name'] for a in book.get('authors', [])]),
                    "languages": book.get('languages', []),
                    "options": available_options
                })

        payload = {"count": len(results), "results": results}
        return Response(json.dumps(payload, ensure_ascii=False),
                        mimetype='application/json; charset=utf-8')

    except Exception as e:
        return Response(json.dumps({"error": str(e)}, ensure_ascii=False),
                        mimetype='application/json; charset=utf-8',
                        status=500)

# ---------------------------------------------------------
# ENDPOINT 2: DOWNLOAD (Custom Filename)
# ---------------------------------------------------------
@app.route('/download/<int:book_id>/<string:fmt_type>', methods=['GET'])
def download_book(book_id, fmt_type):
    if fmt_type not in FORMAT_MAPPING:
        return jsonify({"error": "Invalid format"}), 400

    meta_url = f"{GUTENDEX_API_URL}/{book_id}"
    
    try:
        # 1. Fetch Metadata
        meta_response = requests.get(meta_url)
        if meta_response.status_code == 404:
             return jsonify({"error": "Book not found"}), 404
        
        book_data = meta_response.json()
        
        # 2. Generate Custom Filename
        filename = format_filename(book_data, fmt_type)

        # 3. Find Download URL
        target_mimes = FORMAT_MAPPING[fmt_type]
        download_url = None
        for mime in target_mimes:
            if mime in book_data['formats']:
                download_url = book_data['formats'][mime]
                break
        
        if not download_url:
             return jsonify({"error": "Format not found"}), 404

        # 4. Stream and Serve
        print(f"Downloading: {filename}")
        with requests.get(download_url, stream=True) as r:
            r.raise_for_status()
            return send_file(
                io.BytesIO(r.content),
                mimetype=target_mimes[0],
                as_attachment=True,
                download_name=filename # Matches your requested pattern
            )

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)