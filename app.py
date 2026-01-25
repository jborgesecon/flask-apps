import io
import re
import requests
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
GUTENDEX_API_URL = "https://gutendex.com/books"
GUTENBERG_MIRROR_URL = "https://www.gutenberg.org/ebooks/{}.epub.images"

# Mapping user-friendly format names to Gutenberg MIME types
FORMAT_MAP = {
    'epub': 'application/epub+zip',
    'mobi': 'application/x-mobipocket-ebook',
    'pdf': 'application/pdf',  # Rare on Gutenberg, but valid
    'html': 'text/html',
    'text': 'text/plain'
}

# ---------------------------------------------------------
# HELPER: PARSER
# ---------------------------------------------------------
def parse_search_query(raw_query):
    """
    Parses a string like 'title=metamorphosis lang=en' into 
    Gutendex API parameters.
    """
    params = {}
    search_terms = []

    # Regex to find key=value patterns
    # Matches "key=value" where value can contain spaces if it's not a new key
    pattern = r'(\w+)=(.+?)(?=\s+\w+=|$)'
    matches = list(re.finditer(pattern, raw_query))

    # If no strict syntax found, treat the whole thing as a general search
    if not matches:
        return {"search": raw_query}

    for match in matches:
        key = match.group(1).lower()
        value = match.group(2).strip()

        if key in ['title', 'author', 'search']:
            # Gutendex uses 'search' for both title and author
            # We combine them to narrow the search results
            search_terms.append(value)
        elif key in ['lang', 'language']:
            # Example: 'ger' -> 'de', 'eng' -> 'en' (Simple check, or pass through)
            # Gutendex expects 2-letter codes (en, fr, de)
            params['languages'] = value[:2] 
        elif key == 'year':
            params['author_year_start'] = value
            params['author_year_end'] = value
        elif key == 'topic':
            params['topic'] = value
        elif key == 'format':
            # Map 'epub' -> 'application/epub+zip'
            if value.lower() in FORMAT_MAP:
                params['mime_type'] = FORMAT_MAP[value.lower()]

    # Combine title/author terms into the main search param
    if search_terms:
        params['search'] = " ".join(search_terms)

    return params

# ---------------------------------------------------------
# ENDPOINT 1: SEARCH (ADVANCED)
# ---------------------------------------------------------
@app.route('/search', methods=['GET'])
def search_books():
    """
    Accepts 'q' which can be a simple query or detailed syntax:
    q='title=metamorphosis lang=en format=epub'
    """
    raw_query = request.args.get('q', '')
    if not raw_query:
        return jsonify({"error": "Missing query parameter 'q'"}), 400

    # 1. Parse the user's string into API parameters
    api_params = parse_search_query(raw_query)
    
    # Debug log to see how the parser translated the request
    print(f"Original: '{raw_query}' -> Parsed: {api_params}")

    try:
        # 2. Call Gutendex with the filtered params
        response = requests.get(GUTENDEX_API_URL, params=api_params)
        data = response.json()

        # 3. Parse and simplify results
        results = []
        for book in data.get('results', [])[:5]:
            authors = ", ".join([a['name'] for a in book.get('authors', [])])
            
            # Check available formats for the User
            available_formats = [k for k in book['formats'].keys() if k in FORMAT_MAP.values()]

            results.append({
                "id": book['id'],
                "title": book['title'],
                "authors": authors or "Unknown",
                "languages": book.get('languages'),
                "formats": available_formats  # Useful for debugging
            })

        return jsonify({
            "count": len(results),
            "filters_applied": api_params, # Helpful to show user what we understood
            "results": results
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------------------------------------------------
# ENDPOINT 2: DOWNLOAD (UNCHANGED)
# ---------------------------------------------------------
@app.route('/download/<int:book_id>', methods=['GET'])
def download_book(book_id):
    # (Keep the code exactly as it was in the previous step)
    download_url = GUTENBERG_MIRROR_URL.format(book_id)
    try:
        with requests.get(download_url, stream=True) as r:
            r.raise_for_status()
            file_data = io.BytesIO(r.content)
            return send_file(
                file_data,
                mimetype='application/epub+zip',
                as_attachment=True,
                download_name=f"{book_id}.epub"
            )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)