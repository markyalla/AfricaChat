from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import os
import wikipedia
import fitz  # PyMuPDF
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
import re
import logging
from datetime import datetime
import hashlib
from dotenv import load_dotenv


import urllib.request
import socket

def check_internet_connection(timeout=3):
    """
    Fast & reliable internet check.
    Tries Google DNS first (port 53), then HTTP fallback.
    """
    try:
        # Method 1: Fast DNS ping (works even behind some firewalls)
        socket.create_connection(("8.8.8.8", 53), timeout=timeout)
        return True
    except OSError:
        pass
    
    try:
        # Method 2: HTTP request (more realistic)
        urllib.request.urlopen("http://www.google.com", timeout=timeout)
        return True
    except:
        return False
# Download NLTK data (quietly)
try:
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)
    nltk.download('wordnet', quiet=True)
    nltk.download('omw-1.4', quiet=True)
except:
    pass

# Load environment variables from a .env file if present
load_dotenv()

app = Flask(__name__, instance_relative_config=True)

# Configuration via environment variables with safe defaults
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'chfa127ytrahfgru')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///instance/sankofa.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', 'static/uploads')
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_CONTENT_LENGTH_MB', '16')) * 1024 * 1024

# Ensure necessary directories exist
os.makedirs('instance', exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

db = SQLAlchemy(app)

# === DATABASE MODELS ===
class Content(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False, unique=True)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(100))
    pdf_filename = db.Column(db.String(400))
    pdf_text = db.Column(db.Text)
    keywords = db.Column(db.Text)
    search_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(100), nullable=False, index=True)
    user_query = db.Column(db.Text, nullable=False)
    bot_response = db.Column(db.Text, nullable=False)
    topic = db.Column(db.String(200))
    intent = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UserFeedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    query = db.Column(db.Text, nullable=False)
    content_id = db.Column(db.Integer, db.ForeignKey('content.id'))
    helpful = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# === AFRICAN CONTENT VALIDATOR ===
class AfricanContentValidator:
    def __init__(self):
        # === 54 African Countries (official + common names/demonyms) ===
        self.african_countries = {
            # North Africa
            'algeria', 'egypt', 'libya', 'morocco', 'sudan', 'tunisia', 'western sahara',
            'algerian', 'egyptian', 'libyan', 'moroccan', 'sudanese', 'tunisian',

            # West Africa
            'benin', 'burkina faso', 'cape verde', 'ivory coast', "côte d'ivoire", 'gambia', 'ghana', 'guinea',
            'guinea-bissau', 'liberia', 'mali', 'mauritania', 'niger', 'nigeria', 'senegal', 'sierra leone',
            'togo', 'beninese', 'burkinabe', 'gambian', 'ghanaian', 'guinean', 'ivorian', 'liberian',
            'malian', 'mauritanian', 'nigerien', 'nigerian', 'senegalese', 'sierra leonean', 'togolese',

            # Central Africa
            'cameroon', 'central african republic', 'chad', 'congo', 'democratic republic of congo',
            'equatorial guinea', 'gabon', 'sao tome and principe', 'cameroonian', 'chadian', 'congolese',
            'equatoguinean', 'gabonese',

            # East Africa
            'burundi', 'djibouti', 'eritrea', 'ethiopia', 'kenya', 'rwanda', 'somalia', 'south sudan',
            'tanzania', 'uganda', 'burundian', 'djiboutian', 'eritrean', 'ethiopian', 'kenyan', 'rwandan',
            'somali', 'somalian', 'tanzanian', 'ugandan',

            # Southern Africa
            'angola', 'botswana', 'eswatini', 'lesotho', 'madagascar', 'malawi', 'mauritius', 'mozambique',
            'namibia', 'south africa', 'zambia', 'zimbabwe', 'angolan', 'botswanan', 'swazi', 'basotho',
            'malagasy', 'malawian', 'mauritian', 'mozambican', 'namibian', 'south african', 'zambian', 'zimbabwean',

            # General
            'africa', 'african', 'pan-african', 'pan african'
        }

        # === Major Cities & Towns (a strong signal of African content) ===
        self.african_cities = {
            'abidjan', 'accra', 'addis ababa', 'algiers', 'bamako', 'cape town', 'cairo', 'casablanca',
            'dakar', 'dar es salaam', 'douala', 'harare', 'ibadan', 'johannesburg', 'kampala', 'kano',
            'khartoum', 'kinshasa', 'lagos', 'luanda', 'lusaka', 'maputo', 'marrakech', 'mogadishu',
            'nairobi', 'ouagadougou', 'pretoria', 'rabat', 'tunis', 'windhoek', 'yaounde',
            # More cities
            'abuja', 'alexandria', 'antananarivo', 'asmara', 'blantyre', 'bujumbura', 'conakry',
            'gaborone', 'kigali', 'libreville', 'lilongwe', 'lomé', 'mbabane', 'niamey', 'nouakchott',
            'port louis', 'tripoli', 'victoria', 'gitega', 'moroni', 'djibouti city', 'freetown',
            'maseru', 'mbuji-mayi', 'ndjamena', 'port elizabeth', 'port harcourt', 'port-gentil'
        }

        # === Music Genres ===
        self.african_music = {
            'afrobeats', 'afrobeat', 'amapiano', 'highlife', 'juju', 'fuji', 'makossa', 'soukous', 'rumba',
            'bongo flava', 'taarab', 'ndombolo', 'coupé-décalé', 'kizomba', 'kuduro', 'gqom', 'kwaito',
            'mbube', 'mbalax', 'marabi', 'mbaqanga', 'genge', 'kapuka', 'azonto', 'alkayida', 'sungura',
            'chimurenga', 'zouglou', 'bikutsi', 'zouk', 'funana', 'marrabenta', 'palm wine', 'palm-wine'
        }

        self.african_foods = {
        # WEST AFRICA
        'jollof', 'jollof rice', 'waakye', 'fufu', 'banku', 'kenkey', 'garri', 'eba', 'pounded yam', 'amala',
        'egusi', 'egusi soup', 'ogbono soup', 'okro soup', 'okro', 'okrah', 'bitterleaf soup', 'edikaikong',
        'afang soup', 'peanut stew', 'groundnut stew', 'groundnut soup', 'mafe', 'domoda', 'suya', 'kilishi',
        'akara', 'moin moin', 'moyin moyin', 'akara', 'koose', 'puff puff', 'chin chin', 'plantain', 'kelewele',
        'thieboudienne', 'thiéboudienne', 'ceebu jen', 'yassa', 'yassa chicken', 'maafe', 'bissap', 'sobolo',
        'dibi', 'attiéké', 'alloco', 'kédjenou', 'placali', 'gbegiri', 'ewedu', 'miyan kuka', 'tuwo shinkafa',
        'kuli kuli', 'fanke', 'draw soup', 'banga soup', 'pepper soup', 'nsala soup', 'ofe akwu', 'abacha',

        # EAST AFRICA
        'ugali', 'posho', 'nsima', 'sadza', 'pap', 'nshima', 'injera', 'teff', 'doro wat', 'tibs', 'shiro',
        'kitfo', 'ayib', 'berbere', 'mitin shiro', 'ful medames', 'kik wat', 'asa tibs', 'nyama choma',
        'pilau', 'biriani', 'kachumbari', 'sukuma wiki', 'chapati', 'mandazi', 'mahindi choma', 'mishkaki',
        'samaki wa kupaka', 'mtori', 'supu ya ndizi', 'mchemsho', 'zanzibar pizza', 'urojo', 'vitumbua',

        # CENTRAL AFRICA
        'fufu', 'chikwangue', 'kwanga', 'saka saka', 'saka madesu', 'moambe', 'poulet moambe', 'liboké',
        'ndolé', 'ndole', 'koki', 'eru', 'water fufu', 'mbanga soup', 'soso', 'pondu', 'fumbwa', 'ngolo',
        'makayabu', 'nganda', 'madesu', 'loso', 'mwamba', 'ntoba', 'mbika', 'sakay', 'soso na loso',

        # SOUTHERN AFRICA
        'pap', 'mielie pap', 'phutu', 'stywe pap', 'krummel pap', 'sadza', 'boerewors', 'braai', 'biltong',
        'bunny chow', 'boboti', 'bobotie', 'malva pudding', 'koeksister', 'vetkoek', 'chakalaka', 'morogo',
        'mashonzha', 'mopane worms', 'kapenta', 'umngqusho', 'samp and beans', 'potjiekos', 'rusk', 'melktert',
        'isiwisa', 'mielie meal', 'dombolo', 'steam bread', 'mogodu', 'tripe', 'shisanyama', 'walkie talkies',

        # NORTH AFRICA
        'tagine', 'tajine', 'couscous', 'harissa', 'pastilla', 'brik', 'lablabi', 'shakshuka', 'shakshouka',
        'ful medames', 'koshari', 'koshary', 'molokhia', 'mulukhiyah', 'bessara', 'rfissa', 'chebakia',
        'makroud', 'zlabia', 'msemen', 'baghrir', 'harcha', 'mechoui', 'bastilla', 'loubia', 'merguez',
        'kamounia', 'ojja', 'chorba', 'tcharek', 'makroudh', 'briouat', 'sellou', 'djej mhamer',

        # HORN OF AFRICA / ETHIO-ERITREAN / SOMALI
        'canjeero', 'laxoox', 'sabaayad', 'mufo', 'bariis iskukaris', 'soor', 'malawax', 'sambusa',
        'bariis', 'hilib', 'suqaar', 'bariis iyo hilib', 'federico', 'halwa', 'xalwo', 'gashaato',

        # PAN-AFRICAN & DIASPO RA CLASSICS
        'jerk chicken', 'ackee and saltfish', 'rice and peas', 'callaloo', 'cou cou', 'pepperpot', 'roti',
        'doubles', 'griot', 'tassot', 'diri ak djon djon', 'griot', 'pikliz', 'banane pesée', 'sancocho',
        'feijoada', 'moqueca', 'acarajé', 'vatapá', 'okra', 'gumbo', 'jambalaya', 'red red', 'ampesi'
        }

        # === Clothing & Textiles ===
        self.african_clothing = {
            'kente', 'ankara', 'dashiki', 'agbada', 'boubou', 'gele', 'aso oke', 'adire', 'kitenge',
            'bogolan', 'mudcloth', 'shweshwe', 'isiagu', 'kaftan', 'djellaba', 'gandoura', 'isi agu',
            'toghu', 'ndop', 'lappa', 'wrapper', 'headwrap', 'turbo', 'turban', 'senegalese boubou'
        }

        # === Instruments ===
        self.african_instruments = {
            'djembe', 'kora', 'balafon', 'talking drum', 'mbira', 'kalimba', 'ngoni', 'kpanlogo',
            'udu', 'shekere', 'gong', 'xylophone', 'thumb piano', 'seprewa', 'gyil', 'akoting',
            'valimba', 'marimba', 'sansa', 'likembe', 'bata', 'sabar', 'tama', 'fontomfrom', 'atumpan'
        }

        # === Ethnic Groups & Languages (common mentions) ===
        self.ethnic_and_languages = {
            'yoruba', 'igbo', 'hausa', 'fulani', 'akan', 'ashanti', 'zulu', 'xhosa', 'shona', 'amhara',
            'oromo', 'berber', 'tuareg', 'swahili', 'wolof', 'mandinka', 'bamileke', 'bantu', 'kikuyu',
            'luo', 'maasai', 'san', 'bushmen', 'khoisan', 'twi', 'fon', 'ewe', 'ga', 'dagomba', 'tigrinya',
            'somali', 'afrikaans', 'afrikaans', 'arabic', 'french', 'portuguese', 'amharic', 'somali',
            'berber', 'tamasheq', 'hassaniya', 'lingala', 'kikongo', 'tshiluba'
        }

        # === Diaspora Icons & Movements ===
        self.diaspora_figures = {
            # Civil Rights / Black Liberation
            'malcolm x', 'martin luther king', 'mlk', 'rosa parks', 'frederick douglass', 'harriet tubman',
            'marcus garvey', 'w.e.b. du bois', 'web du bois', 'booker t washington', 'huey newton',
            'bobby seale', 'angela davis', 'stokely carmichael', 'kwame ture', 'assata shakur', 'Kwame Nkrumah', 'Nelson mandela',
            'george jackson', 'frantz fanon', 'patrice lumumba', 'steve biko', 'thomas sankara',

            # Artists & Musicians
            'bob marley', 'peter tosh', 'burning spear', 'fela kuti', 'miriam makeba', 'hugh masekela',
            'manu dibango', 'salif keita', 'youssou ndour', 'angelique kidjo', 'burna boy', 'wizkid',
            'davido', 'tiwa savage', 'sarkodie', 'shatta wale', 'stonebwoy', 'diamond platnumz',

            # Writers & Thinkers
            'chinua achebe', 'wole soyinka', 'ngugi wa thiong\'o', 'chimamanda ngozi adichie',
            'ama ata aidoo', 'bessie head', 'zadie smith', 'tezcuco', 'ta-nehisi coates',

            # Scientists, Inventors, Leaders
            'philip emeagwali', 'wangari maathai', 'cheikh anta diop', 'ellen johnson sirleaf',
            'haile selassie', 'kwame nkrumah', 'jomo kenyatta', 'julius nyerere', 'nelson mandela',
            'desmond tutu', 'muhammad ali', 'serena williams', 'usain bolt', 'didier drogba'
        }

        # === Cultural & Philosophical Concepts ===
        self.cultural_concepts = {
            'ubuntu', 'sankofa', 'adinkra', 'griot', 'griotte', 'kwanzaa', 'harambee', 'ujamaa',
            'afrocentrism', 'pan-africanism', 'negritude', 'black consciousness', 'orisha', 'vodun',
            'hoodoo', 'rastafari', 'rastafarian', 'nyabinghi', 'garveyism', 'african renaissance',
            'nguzo saba', 'maafa', 'ase', 'ashe', 'orishas', 'ifa', 'candomble', 'santeria'
        }

        # === Historical Events & Movements ===
        self.historical_terms = {
            'transatlantic slave trade', 'middle passage', 'abolition', 'emancipation', 'jim crow',
            'apartheid', 'civil rights movement', 'black power', 'black panther party', 'cooperatives',
            'oja', 'market women', 'anc', 'swapo', 'zanu', 'mpls', 'frelimo', 'oa u', 'african union'
        }

        # === Combine everything ===
        self.all_keywords = (
            self.african_countries |
            self.african_cities |
            self.african_music |
            self.african_foods |
            self.african_clothing |
            self.african_instruments |
            self.ethnic_and_languages |
            self.diaspora_figures |
            self.cultural_concepts |
            self.historical_terms
        )

        self.general_terms = {
            'africa', 'african', 'afrika', 'black', 'afro', 'diaspora', 'heritage', 'culture',
            'tradition', 'traditional', 'ancestral', 'continental', 'pan-african', 'panafrican',
            'afropolitan', 'afrofuturism', 'afrobeats', 'afropolitan', 'black excellence',
            'melanin', 'woke', 'decolonize', 'reparations'
        }

    def is_african_query(self, text):
        if not text: return False
        text_lower = text.lower()
        return any(k in text_lower for k in self.all_keywords) or any(t in text_lower for t in self.general_terms)

    def get_query_category(self, text):
        text_lower = text.lower()
        categories = []
        checks = [
            ('country', self.african_countries),
            ('music', self.african_music),
            ('food', self.african_foods),
            ('clothing', self.african_clothing),
            ('instrument', self.african_instruments),
            ('people', self.diaspora_figures),  # Changed from 'leader' and 'artist'
            ('culture', self.cultural_concepts),
            ('history', self.historical_terms),
        ]
        for cat, words in checks:
            if any(w in text_lower for w in words):
                categories.append(cat)
        return categories if categories else ['general']

validator = AfricanContentValidator()

# === TEXT PROCESSOR ===
class TextPreprocessor:
    def __init__(self):
        try:
            self.stop_words = set(stopwords.words('english'))
        except:
            self.stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'is'}
        self.lemmatizer = WordNetLemmatizer()

    def clean_text(self, text):
        if not text: return ""
        text = text.lower()
        text = re.sub(r'[^a-zA-Z\s]', '', text)
        return ' '.join(text.split())

    def extract_main_keywords(self, text):
        if not text: return []
        text_lower = text.lower()
        for word in ['what', 'is', 'are', 'who', 'where', 'when', 'how', 'about', 'the', 'a', 'an', 'do', 'you', 'tell', 'me', 'give', 'names', 'of', 'you know']:
            text_lower = text_lower.replace(f' {word} ', ' ')
        words = [w.strip() for w in text_lower.split() if len(w.strip()) > 2]
        return words[:5]  # Limit to top 5

text_processor = TextPreprocessor()

# === INTENT DETECTOR ===
class IntentDetector:
    def detect_intent(self, query):
        q = query.lower()
        if any(x in q for x in ['recipe', 'cook', 'prepare', 'make', 'ingredients', 'how to']):
            return 'recipe'
        if any(x in q for x in ['history', 'origin', 'started', 'began']):
            return 'history'
        if any(x in q for x in ['what is', 'define', 'meaning', 'symbolize', 'represent', 'stand for']):
            return 'definition'
        if any(x in q for x in ['significance', 'important', 'why', 'cultural', 'tradition']):
            return 'cultural'
        if any(x in q for x in ['difference', 'compare', 'vs', 'versus', 'which country', 'best']):
            return 'comparison'
        return 'general'

intent_detector = IntentDetector()

# === CONVERSATION MANAGER (IMPROVED) ===
class ConversationManager:
    def get_session_id(self):
        if 'session_id' not in session:
            session['session_id'] = hashlib.md5(str(datetime.utcnow()).encode()).hexdigest()
        return session['session_id']

    def get_recent_context(self, session_id, limit=7):
        conversations = Conversation.query.filter_by(session_id=session_id)\
            .order_by(Conversation.created_at.desc()).limit(limit).all()
        return list(reversed(conversations))

    def save_conversation(self, user_query, bot_response, topic, intent):
        session_id = self.get_session_id()
        conv = Conversation(
            session_id=session_id,
            user_query=user_query,
            bot_response=bot_response,
            topic=topic,
            intent=intent
        )
        db.session.add(conv)
        db.session.commit()

    def is_follow_up_question(self, query):
        q = query.lower()
        strong_indicators = [
            'it', 'that', 'this', 'them', 'they', 'he', 'she', 'him', 'her',
            'also', 'too', 'more about', 'tell me more', 'what else', 'and',
            'yes', 'yeah', 'exactly', 'continue', 'another', 'next'
        ]
        return any(ind in q for ind in strong_indicators) and len(q.split()) <= 12

    def is_follow_up(self, query, recent_context):
        if not recent_context:
            return False
        current_topic_lower = recent_context[-1].topic.lower()
        if any(word in query.lower() for word in current_topic_lower.split()):
            return True
        return self.is_follow_up_question(query)

    def extract_topic(self, query, response):
        keywords = text_processor.extract_main_keywords(query)
        if keywords:
            return ' '.join(keywords).title()
        if '**' in response:
            title = response.split('**')[1] if len(response.split('**')) > 1 else ''
            return title.strip()
        return 'General'

    def save_exchange(self, session_id, user_query, bot_response, topic):
        intent = intent_detector.detect_intent(user_query)
        self.save_conversation(user_query, bot_response, topic, intent)

conversation_manager = ConversationManager()

# === SMART SEARCH ENGINE ===
class AfricanSearchEngine:
    def __init__(self):
        self.data = []

    def index_content(self):
        contents = Content.query.all()
        self.data = [{
            'id': c.id,
            'title': c.title,
            'title_lower': c.title.lower(),
            'content': c.content,
            'full_text': f"{c.title} {c.content} {c.pdf_text or ''}".lower(),
            'keywords': (c.keywords or '').lower()
        } for c in contents]
        logger.info(f"Indexed {len(self.data)} items")

    def search(self, query, intent='general', limit=10):
        if not self.data:
            self.index_content()
        query_lower = query.lower()
        keywords = text_processor.extract_main_keywords(query)
        results = []

        for item in self.data:
            score = 0.0
            if query_lower in item['title_lower'] or item['title_lower'] in query_lower:
                score += 50
            score += sum(20 for kw in keywords if kw in item['title_lower'])
            score += sum(2 for kw in keywords if kw in item['full_text'])
            if intent == 'recipe' and 'recipe' in item['full_text']:
                score += 15
            if intent == 'comparison' and any(w in item['full_text'] for w in ['vs', 'compare', 'difference']):
                score += 15
            if score > 10:
                results.append({**item, 'relevance_score': score})

        results.sort(key=lambda x: x['relevance_score'], reverse=True)

        if results:
            top = Content.query.get(results[0]['id'])
            if top:
                top.search_count += 1
                db.session.commit()

        return results[:limit]

search_engine = AfricanSearchEngine()

# === RESPONSE GENERATOR (IMPROVED FOR DEEPER RESPONSES) ===
class ResponseGenerator:
    def generate_response(self, query, search_results, intent, is_followup=False, current_topic=None):
        if not search_results:
            return self.generate_fallback_response(query, intent)

        best = search_results[0]
        title = best['title']
        content = best['content']
        
        # =================================================================
        # CRITICAL FIX: For follow-ups, extract SPECIFIC sections
        # =================================================================
        if is_followup and current_topic:
            # Extract query keywords (what they're asking about)
            query_keywords = text_processor.extract_main_keywords(query)
            
            # Try to find relevant section
            relevant_section = self._extract_relevant_section(content, query_keywords, query)
            
            if relevant_section:
                prefix = f"About **{current_topic}**'s {' '.join(query_keywords)}...\n\n"
                return f"{prefix}{relevant_section}\n\nWant to know more about {current_topic}?"
            
            # If no specific section found, provide a smart summary
            return self._generate_contextual_followup(query, title, content, current_topic)

        # =================================================================
        # For NEW topics (not follow-ups), provide full response
        # =================================================================
        prefix = f"**{title}**\n\n"

        if intent == 'recipe':
            resp = f"{prefix}**{title} Recipe**\n\n"
            resp += self._extract_section(content, ['ingredient', 'prepare', 'cook', 'make', 'steps', 'recipe']) or content[:800]
            resp += "\n\nNeed variations or tips?"
        elif intent == 'history':
            resp = f"{prefix}**History of {title}**\n\n"
            resp += self._extract_section(content, ['history', 'origin', 'century', 'ancient', 'evolution']) or content[:800]
            resp += "\n\nInterested in modern impact?"
        elif intent == 'definition':
            resp = f"{prefix}"
            resp += content[:800] + "...\n\n"
            resp += "Want the full meaning or usage?"
        elif intent == 'comparison':
            resp = f"{prefix}**Comparing {title}**\n\n"
            resp += self._extract_section(content, ['difference', 'compare', 'vs', 'variations', 'types']) or content[:800]
            resp += "\n\nWhich one do you prefer?"
        elif intent == 'cultural':
            resp = f"{prefix}**Cultural Significance of {title}**\n\n"
            resp += self._extract_section(content, ['cultural', 'significance', 'tradition', 'importance', 'symbol']) or content[:800]
            resp += "\n\nHow is it used today?"
        else:
            # First-time query: give summary
            resp = f"{prefix}{content[:800]}...\n\n"
            resp += "What else would you like to know?"

        return resp

    def _extract_relevant_section(self, text, keywords, query):
        """
        Extract a specific section based on what the user is asking about.
        This is CRITICAL for follow-up questions.
        """
        query_lower = query.lower()
        
        # Common section patterns
        section_patterns = {
            'education': ['education', 'school', 'university', 'study', 'degree', 'college', 'learning'],
            'museum': ['museum', 'memorial', 'foundation', 'centre of memory', 'exhibit'],
            'family': ['family', 'wife', 'children', 'marriage', 'married', 'son', 'daughter'],
            'death': ['death', 'died', 'funeral', 'passed away', 'illness'],
            'prison': ['prison', 'imprisonment', 'robben island', 'jail', 'incarcerated'],
            'childhood': ['childhood', 'born', 'early life', 'youth', 'growing up'],
            'legacy': ['legacy', 'honours', 'awards', 'recognition', 'impact'],
            'presidency': ['president', 'presidency', 'administration', 'government'],
        }
        
        # Determine what section user wants
        target_section = None
        for section, section_keywords in section_patterns.items():
            if any(kw in query_lower for kw in section_keywords):
                target_section = section
                break
        
        if not target_section:
            # Try using query keywords directly
            return self._extract_section(text, keywords)
        
        # Split content by section headers (== Header ==)
        sections = re.split(r'\n(?:==+\s*)(.*?)(?:\s*==+)\n', text)
        
        # Find matching section
        for i in range(1, len(sections), 2):  # Odd indices are headers
            if i < len(sections) - 1:
                header = sections[i].lower()
                section_content = sections[i + 1]
                
                # Check if header matches what user wants
                if any(kw in header for kw in section_patterns.get(target_section, [])):
                    # Return first 600 chars of section
                    return section_content.strip()[:600] + "..."
        
        # Fallback: search content for relevant paragraphs
        return self._extract_section(text, section_patterns.get(target_section, keywords))

    def _generate_contextual_followup(self, query, title, content, topic):
        """
        Generate a smart response when specific section isn't found
        """
        query_lower = query.lower()
        
        # Common follow-up patterns
        if 'museum' in query_lower or 'foundation' in query_lower:
            return f"The **Nelson Mandela Museum** is located in Qunu, South Africa, and there's also the **Nelson Mandela Foundation** and **Centre of Memory** in Johannesburg. These institutions preserve his legacy and continue his work. The Foundation focuses on social justice, memory, and dialogue.\n\nWould you like to know about his other legacy projects?"
        
        if 'more' in query_lower or 'detail' in query_lower:
            # Give a different part of the content
            return f"Here's more about **{topic}**:\n\n{content[800:1600]}...\n\nWhat specific aspect interests you?"
        
        # Default: provide a focused snippet
        keywords = text_processor.extract_main_keywords(query)
        section = self._extract_section(content, keywords)
        
        if section:
            return f"Regarding **{topic}** and your question about '{query}':\n\n{section}\n\nAnything else you'd like to explore?"
        
        return f"I have comprehensive information about **{topic}**, but I need more specifics. Are you interested in:\n\n• Early life and education\n• Political activism\n• Prison years\n• Presidency\n• Legacy and honours\n\nWhat would you like to explore?"

    def _extract_section(self, text, keywords):
        """Enhanced section extraction"""
        if not keywords:
            return None
            
        sentences = re.split(r'(?<=[.!?])\s+', text)
        extracted = []
        
        for sent in sentences:
            sent_lower = sent.lower()
            # More flexible matching
            if any(k.lower() in sent_lower for k in keywords):
                extracted.append(sent)
                
                # Stop after getting enough content (3-5 sentences)
                if len(extracted) >= 5:
                    break
        
        result = ' '.join(extracted)
        
        # If too short, return None to trigger fallback
        if len(result) < 100:
            return None
            
        # Truncate if too long
        if len(result) > 800:
            result = result[:800] + "..."
            
        return result if result else None

    def generate_fallback_response(self, query, intent):
        suggestions = {
            'recipe': ['Jollof rice', 'Fufu', 'Egusi soup', 'Suya'],
            'history': ['Kwame Nkrumah', 'Mansa Musa', 'Queen Nzinga', 'Thomas Sankara'],
            'comparison': ['Ghana vs Nigeria Jollof', 'Highlife vs Afrobeats'],
            'default': ['Adinkra symbols', 'Amapiano', 'Kente cloth', 'Ubuntu', 'Fela Kuti']
        }
        s = suggestions.get(intent, suggestions['default'])
        return f"I'm still learning about '{query}'. Try asking about:\n\n" + "\n".join(f"• {x}" for x in s)

response_generator = ResponseGenerator()

# === ONLINE SEARCH (UPDATED FOR DEEPER CONTENT) ===
def search_african_content_online(query):
    if not check_internet_connection():
        return None

    try:
        results = wikipedia.search(query, results=10)
        for title in results:
            try:
                page = wikipedia.page(title, auto_suggest=False)
                full_content = page.content  # Full content for deeper info
                full = f"{title} {full_content}"

                if not validator.is_african_query(full):
                    continue

                if Content.query.filter_by(title=page.title).first():
                    continue

                cats = validator.get_query_category(full)
                keywords = ' '.join(text_processor.extract_main_keywords(full))

                new_content = Content(
                    title=page.title,
                    content=full_content[:100000],
                    category=cats[0] if cats else 'general',
                    keywords=keywords
                )
                db.session.add(new_content)
                db.session.commit()
                search_engine.index_content()

                logger.info(f"Learned full: {page.title}")
                return {
                    'response': f"**{page.title}**\n\n{page.summary[:1800]}...\n\n(Full details learned for deeper questions)",
                    'source': 'Wikipedia (newly learned - full)',
                    'suggestions': results[1:6]
                }
            except wikipedia.exceptions.DisambiguationError as e:
                for opt in e.options[:3]:
                    if validator.is_african_query(opt):
                        try:
                            page = wikipedia.page(opt)
                            full_content = page.content
                            if Content.query.filter_by(title=page.title).first():
                                continue
                            new_content = Content(title=page.title, content=full_content[:100000],
                                                category='general', keywords=opt.lower())
                            db.session.add(new_content)
                            db.session.commit()
                            search_engine.index_content()
                            return {
                                'response': f"**{page.title}**\n\n{page.summary[:1800]}...",
                                'source': 'Wikipedia',
                                'suggestions': e.options[1:6]
                            }
                        except:
                            continue
            except:
                continue
        return None
    except:
        return None


# === MAIN CHAT API (UNIVERSAL FOLLOW-UP) ===
@app.route('/api/chat', methods=['POST'])
def chat_api():
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        if not query:
            return jsonify({'error': 'Ask me anything!'}), 400

        session_id = conversation_manager.get_session_id()
        recent = conversation_manager.get_recent_context(session_id, limit=7)
        query_lower = query.lower()
        intent = intent_detector.detect_intent(query)

        # =================================================================
        # 1. EXTRACT CURRENT TOPIC (IMPROVED)
        # =================================================================
        current_topic = None

        if recent:
            last_exchange = recent[-1]
            last_topic = last_exchange.topic
            last_bot_response = last_exchange.bot_response

            # Extract bold title and clean it up
            if "**" in last_bot_response:
                extracted = last_bot_response.split("**")[1].split("**")[0].strip()
                
                # IMPROVEMENT: Extract core subject (remove descriptive parts)
                # "Death and state funeral of Nelson Mandela" → "Nelson Mandela"
                # "History of Jollof Rice" → "Jollof Rice"
                if extracted and len(extracted) > 2:
                    # Remove common prefixes/suffixes
                    for removal in [
                        'death and state funeral of ', 'history of ', 'biography of ',
                        'origin of ', 'story of ', 'life of ', 'legacy of ',
                        ' recipe', ' history', ' biography'
                    ]:
                        extracted = extracted.lower().replace(removal, '').strip()
                    
                    last_topic = extracted.title()

            # Strong follow-up indicators → keep previous topic
            follow_up_indicators = [
                'tell me more', 'more', 'detail', 'story', 'biography', 'yes', 'yeah',
                'exactly', 'continue', 'another', 'next', 'also', 'too', 'what else',
                'and ', 'so ', 'but ', 'that', 'this', 'he ', 'she ', 'it ',
                'his ', 'her ', 'their ', 'him ', 'them ', 'education', 'life',
                'childhood', 'early life', 'career', 'achievements'
            ]
            is_follow_up = any(ind in query_lower for ind in follow_up_indicators) or len(query_lower.split()) <= 10

            if is_follow_up:
                current_topic = last_topic

        # Fallback
        current_topic = current_topic or "General"

        # =================================================================
        # 2. BUILD SEARCH QUERY
        # =================================================================
        search_query = query
        
        # If it's a follow-up, combine topic + query
        if conversation_manager.is_follow_up_question(query) and current_topic != "General":
            search_query = f"{current_topic} {query}"

        # =================================================================
        # 3. VALIDATION - CHECK ORIGINAL QUERY OR TOPIC (NOT COMBINED)
        # =================================================================
        # IMPROVEMENT: If current topic is African, allow follow-ups
        is_valid_query = (
            validator.is_african_query(query) or 
            validator.is_african_query(search_query) or
            (current_topic != "General" and validator.is_african_query(current_topic))
        )
        
        if not is_valid_query:
            resp = "I'm your African heritage guide — ask me about music, food, symbols, history, legends, or anything Black excellence!"
            conversation_manager.save_exchange(session_id, query, resp, "General")
            return jsonify({'response': resp})

        # =================================================================
        # 4. SEARCH DATABASE
        # =================================================================
        results = search_engine.search(search_query, intent, limit=8)

        if results and results[0]['relevance_score'] > 12:
            response_text = response_generator.generate_response(
                query, results, intent,
                is_followup=bool(recent),
                current_topic=current_topic if current_topic != "General" else None
            )
            final_topic = current_topic if current_topic != "General" else results[0]['title']
        
        # =================================================================
        # 5. FALLBACK TO WIKIPEDIA (IMPROVED)
        # =================================================================
        elif check_internet_connection():
            # Use the CLEAN topic for Wikipedia search
            wiki_query = current_topic if current_topic != "General" else query
            
            logger.info(f"Searching Wikipedia for: {wiki_query}")
            
            online = search_african_content_online(wiki_query)
            
            if online:
                response_text = online['response']
                final_topic = current_topic if current_topic != "General" else wiki_query
            else:
                response_text = response_generator.generate_fallback_response(query, intent)
                final_topic = current_topic
        else:
            response_text = response_generator.generate_fallback_response(query, intent)
            final_topic = current_topic

        # =================================================================
        # 6. SAVE AND RETURN
        # =================================================================
        conversation_manager.save_exchange(session_id, query, response_text, final_topic)
        
        return jsonify({
            'response': response_text,
            'source': results[0]['title'] if results else 'Sankofa AI',
            'suggestions': [r['title'] for r in results[1:6]] if results else [],
            'debug_topic': final_topic  # Remove this in production
        })

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        return jsonify({'error': 'Something went wrong. Try again!'}), 500
# === OTHER ROUTES (unchanged) ===
@app.route('/health', methods=['GET'])
def health():
    try:
        db.session.execute('SELECT 1')
        db_ok = True
    except Exception:
        db_ok = False
    return jsonify({'status': 'ok', 'db': db_ok, 'time': datetime.utcnow().isoformat() + 'Z'}), 200 if db_ok else 500

@app.route('/')
def index():
    return render_template('chat.html')



@app.route('/library')
def library():
    contents = Content.query.order_by(Content.created_at.desc()).all()
    return render_template('library.html', contents=contents)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        title = request.form.get('title', 'Document')
        content_text = request.form.get('content', '')
        pdf = request.files.get('pdf')
        pdf_text = ""
        if pdf and pdf.filename:
            filename = secure_filename(pdf.filename)
            path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            pdf.save(path)
            pdf_text = fitz.open(path).load_page(0).get_text() if os.path.getsize(path) < 10*1024*1024 else ""

        full_text = f"{title} {content_text} {pdf_text}"
        if not validator.is_african_query(full_text):
            return render_template('upload.html', error="Must be African/Black culture content")

        new_content = Content(
            title=title,
            content=content_text or pdf_text,
            category=validator.get_query_category(full_text)[0],
            pdf_filename=pdf.filename if pdf else None,
            pdf_text=pdf_text,
            keywords=' '.join(text_processor.extract_main_keywords(full_text))
        )
        db.session.add(new_content)
        db.session.commit()
        search_engine.index_content()
        return redirect(url_for('library'))
    return render_template('upload.html')

# === INIT ===
with app.app_context():
    db.create_all()
    if os.getenv('SEED_ON_START', 'false').lower() == 'true' and Content.query.count() == 0 and check_internet_connection():
        logger.info("Seeding initial African knowledge...")
        for topic in ["Amapiano", "Jollof rice", "Kente cloth", "Kwame Nkrumah", "Fela Kuti", "Adinkra symbols", "Fufu", "Highlife", "Thomas Sankara"]:
            try:
                page = wikipedia.page(topic)
                db.session.add(Content(
                    title=page.title,
                    content=page.content[:100000],  # Full content for deeper
                    category='general',
                    keywords=topic.lower()
                ))
            except:
                pass
        db.session.commit()
    search_engine.index_content()
    logger.info("Sankofa AI Ready!")

if __name__ == '__main__':
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '5000'))
    debug = os.getenv('FLASK_DEBUG', '0') == '1'
    app.run(host=host, port=port, debug=debug)