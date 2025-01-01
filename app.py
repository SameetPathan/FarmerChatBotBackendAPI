import datetime
import urllib
import os
import firebase_admin
import requests
from anthropic import Anthropic
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from firebase_admin import credentials, db
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

cred = credentials.Certificate("jarvis-systems-commons-firebase-adminsdk-7qghi-24244ca155.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://jarvis-systems-commons-default-rtdb.firebaseio.com'
})

LANGUAGE_CODES = {
    'hindi': 'hi',
    'marathi': 'mr',
    'telugu': 'te',
    'kannada': 'kn',
    'tamil': 'ta',
    'arabic': 'ar',
    'bengali': 'bn',
    'bhojpuri': 'bho',
    'gujarati': 'gu',
    'konkani': 'kok',
    'malayalam': 'ml',
    'nepali': 'ne',
    'punjabi': 'pa',
    'sanskrit': 'sa',
    'urdu': 'ur',
    'english': 'en'
}


def translate_from_english(text, target_language):
    try:
        translator = GoogleTranslator(source='english', target=target_language)
        translated_text = translator.translate(text)
        return translated_text
    except Exception as e:
        return f"Translation Error: {str(e)}"


def translate_text(text, source_language):
    try:
        translator = GoogleTranslator(source=source_language, target='english')
        translated_text = translator.translate(text)
        return translated_text
    except Exception as e:
        return f"Translation Error: {str(e)}"


def get_google_search_content(query):
    try:
        search_query = urllib.parse.quote(query)
        url = f"https://www.google.com/search?q={search_query}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            search_results = soup.find_all('div', class_='g')
            description = []
            for result in search_results[:5]:
                snippet = result.find('div', class_='VwiC3b')
                if snippet:
                    description.append(snippet.text)
            final_description = "\n\n".join(description)
            return final_description
        else:
            return None
    except Exception as e:
        print("Error:", str(e))
        return None


def store_in_firebase(phone_number, query, response, source_language):
    try:
        ref = db.reference(f'Agriculture/users/{phone_number}/messages')
        new_message = {
            'timestamp': datetime.datetime.now().isoformat(),
            'query': query,
            'response': response,
            'language': source_language
        }
        ref.push(new_message)
        return True
    except Exception as e:
        print(f"Firebase error: {str(e)}")
        return False


@app.route('/agriculture/chat', methods=['POST'])
def chat_endpoint():
    try:
        data = request.json
        source_language = data.get('source_language', '').lower()
        query = data.get('query', '')
        user_phone = data.get('userphone', '')
        print(request.json)
        if not all([source_language, query, user_phone]):
            return jsonify({
                'success': False,
                'message': 'Missing required parameters'
            })

        if source_language not in LANGUAGE_CODES:
            return jsonify({
                'success': False,
                'message': 'Unsupported language'
            })

        english_query = query
        if source_language != 'english':

            english_query = translate_text(query, LANGUAGE_CODES[source_language])
            if not english_query:
                return jsonify({
                    'success': False,
                    'message': 'Translation failed'
                })
        print(english_query)
        search_content = get_google_search_content(english_query)
        print(search_content)
        anthropic = Anthropic(
            api_key=os.environ.get('AnthropicApiKey'))
        prompt = f"""You are an AI agricultural expert tasked with providing comprehensive and practical advice based on a given query and recent search results. Your goal is to offer clear, actionable information that addresses the user's question while incorporating relevant details from the provided search content.

            Here is the search content related to the query:
            <search_content>
            {search_content}
            </search_content>
            
            Carefully analyze the search content, focusing on the following aspects:
            1. Identify key information relevant to the query
            2. Note any statistical data, research findings, or expert opinions
            3. Look for practical advice, best practices, or innovative techniques
            4. Consider any regional or climate-specific information
            
            Now, address the following query:
            <query>
            {english_query}
            </query>
            
            When formulating your response:
            1. Directly answer the query using information from the search content
            2. Provide practical, actionable advice for farmers or agricultural professionals
            3. Include relevant statistics or research findings to support your recommendations
            4. Consider potential challenges or limitations and offer solutions when possible
            5. If appropriate, suggest sustainable or environmentally friendly practices
            6. Avoid speculation or information not supported by the provided content
            
            Present your answer in the following format strictly respond in below format only do not add any additional information before or after tags :
            <agricultural_advice>
            [Your comprehensive answer here, structured in clear paragraphs]
            </agricultural_advice>
            
            Ensure your response is thorough, informative, and tailored to the specific query while leveraging the provided search content."""

        ai_response = anthropic.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": prompt
            }],
            system="You are an agricultural expert. Provide clear and practical advice based on the query and search results."
        )
        print(ai_response)

        english_response = ai_response.content[0].text


        final_response = english_response
        if source_language != 'english':
            final_response = translate_from_english(english_response, LANGUAGE_CODES[source_language])
            if not final_response:
                return jsonify({
                    'success': False,
                    'message': 'Response translation failed'
                })

        storage_success = store_in_firebase(user_phone, query, final_response, source_language)

        return jsonify({
            'success': True,
            'message': final_response,
            'storage_success': storage_success
        })

    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        if source_language != 'english':
            error_message = translate_text(error_message, 'en', LANGUAGE_CODES[source_language])

        return jsonify({
            'success': False,
            'message': error_message
        })


if __name__ == '__main__':
    app.run(debug=True)
