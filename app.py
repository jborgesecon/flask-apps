import io
import requests
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
GUTENDEX_API_URL = "https://gutendex.com/books"
# We use a reliable mirror for direct file downloads
GUTENBERG_MIRROR_URL = "https://www.gutenberg.org/ebooks/{}.epub.images"

# ---------------------------------------------------------
# ENDPOINT 1: SEARCH
# ---------------------------------------------------------
@app.route('/search', methods=['GET'])
def search_books():
    """
    Receives a query (e.g., 'Metamorphosis'), asks Gutendex,
    and returns a simplified list of results.
    """
    query = request.args.get('q')
    if not query:
        return jsonify({"error": "Missing query parameter 'q'"}), 400

    try:
        # 1. Forward the search to Gutendex
        response = requests.get(GUTENDEX_API_URL, params={"search": query})
        data = response.json()

        # 2. Parse and simplify the results
        results = []
        for book in data.get('results', [])[:5]: # Limit to top 5 results
            
            # Format author names nicely
            authors = ", ".join([a['name'] for a in book.get('authors', [])])
            
            results.append({
                "id": book['id'],
                "title": book['title'],
                "authors": authors or "Unknown",
                "copyright": book.get('copyright')
            })

        return jsonify({"count": len(results), "results": results})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------------------------------------------------
# ENDPOINT 2: DOWNLOAD
# ---------------------------------------------------------
@app.route('/download/<int:book_id>', methods=['GET'])
def download_book(book_id):
    """
    Fetches the .epub file from a Gutenberg mirror into RAM,
    then pipes it directly to the user.
    """
    download_url = GUTENBERG_MIRROR_URL.format(book_id)
    print(f"Fetching from: {download_url}") # Debug log

    try:
        # 1. Stream the file from the mirror (don't download all at once yet)
        with requests.get(download_url, stream=True) as r:
            r.raise_for_status()
            
            # 2. Load content into RAM (BytesIO)
            # Since .epubs are small (mostly <1MB), RAM is fine.
            file_data = io.BytesIO(r.content)
            
            # 3. Serve the file directly to the client
            return send_file(
                file_data,
                mimetype='application/epub+zip',
                as_attachment=True,
                download_name=f"{book_id}.epub"
            )

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return jsonify({"error": "Book file not found on mirror"}), 404
        return jsonify({"error": "Failed to fetch book from mirror"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Running on 0.0.0.0 to be accessible if we containerize it later
    app.run(host='0.0.0.0', port=5000, debug=True)