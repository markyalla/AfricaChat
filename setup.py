#!/usr/bin/env python3
"""
Sankofa AI Setup and Test Script
This script helps initialize the application and add sample content
"""

import os
import sys
import sqlite3
from datetime import datetime

def create_directories():
    """Create necessary directories"""
    directories = [
        'static/uploads',
        'static/images',
        'templates'
    ]
    
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"✓ Created directory: {directory}")
        else:
            print(f"✓ Directory exists: {directory}")

def check_dependencies():
    """Check if all required packages are installed"""
    required_packages = [
        'flask', 'flask_sqlalchemy', 'flask_admin',
        'pandas', 'sklearn', 'nltk', 'fitz', 'wikipedia'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✓ {package} is installed")
        except ImportError:
            missing_packages.append(package)
            print(f"✗ {package} is missing")
    
    if missing_packages:
        print("\nPlease install missing packages:")
        print("pip install " + " ".join(missing_packages))
        return False
    
    return True

def setup_nltk():
    """Download required NLTK data"""
    try:
        import nltk
        
        nltk_data = ['punkt', 'stopwords', 'wordnet', 'omw-1.4']
        
        for data in nltk_data:
            try:
                nltk.data.find(f'tokenizers/{data}' if data == 'punkt' else f'corpora/{data}')
                print(f"✓ NLTK {data} already available")
            except LookupError:
                print(f"Downloading NLTK {data}...")
                nltk.download(data, quiet=True)
                print(f"✓ NLTK {data} downloaded")
                
    except Exception as e:
        print(f"Error setting up NLTK: {e}")
        return False
    
    return True

def create_sample_content():
    """Add sample African history content to the database"""
    
    sample_content = [
        {
            'title': 'Ancient Kingdom of Kush',
            'content': '''The Kingdom of Kush was an ancient African kingdom situated on the confluences of the Blue and White Nile, and the River Atbara in what is now the Republic of Sudan. Established after the Bronze Age collapse and the disintegration of the New Kingdom of Egypt, it was centered at Napata in its early phase. The Kushite rulers adopted many Egyptian customs and were buried in pyramid tombs. They conquered Egypt and ruled as the Twenty-fifth Dynasty of Egypt for nearly a century.''',
            'keywords': 'kush,ancient,egypt,sudan,napata,dynasty,pharaoh,africa',
            'africa_score': 5.0
        },
        {
            'title': 'Great Zimbabwe Civilization',
            'content': '''Great Zimbabwe was a medieval city in the south-eastern hills of today's Zimbabwe near Lake Mutirikwi and the town of Masvingo. It was the capital of the Kingdom of Zimbabwe during the country's Late Iron Age. Construction on the monument began in the 11th century and continued until the 15th century. The ruins are divided into three distinct areas: the Hill Complex, the Great Enclosure, and the Valley Ruins. The site is famous for its massive stone walls built without mortar.''',
            'keywords': 'zimbabwe,medieval,iron age,stone walls,architecture,africa',
            'africa_score': 4.5
        },
        {
            'title': 'Mali Empire and Mansa Musa',
            'content': '''The Mali Empire was an empire in West Africa from c. 1235 to 1600. The empire was founded by Sundiata Keita and became renowned for the wealth of its rulers, especially Mansa Musa. Mansa Musa (r. c. 1312 – c. 1337) was the tenth mansa of the Mali Empire, a Islamic West African state. During his reign, Mali was one of the richest countries in the world, and Mansa Musa is believed to have been among the wealthiest individuals in history.''',
            'keywords': 'mali,mansa musa,west africa,empire,sundiata keita,wealth,islam',
            'africa_score': 5.0
        },
        {
            'title': 'Ethiopian Orthodox Christianity',
            'content': '''Ethiopian Orthodox Christianity has ancient roots in Ethiopia, dating back to the 4th century when the Kingdom of Aksum converted to Christianity. The Ethiopian Orthodox Tewahedo Church is one of the oldest Christian communities in the world. Ethiopia is mentioned numerous times in the Bible, and the Ethiopian Orthodox Church claims that the Ark of the Covenant rests in the Church of Our Lady Mary of Zion in Aksum.''',
            'keywords': 'ethiopia,orthodox,christianity,aksum,church,ancient,religion',
            'africa_score': 4.0
        },
        {
            'title': 'Swahili Coast Trade Networks',
            'content': '''The Swahili Coast refers to the eastern coast of Africa from Somalia to Mozambique. From the 8th century onwards, this region became an important part of the Indian Ocean trade networks. Swahili city-states like Kilwa, Mombasa, and Zanzibar became wealthy trading centers, dealing in gold, ivory, and slaves. The Swahili culture represents a unique blend of African, Arab, and Persian influences.''',
            'keywords': 'swahili,coast,trade,kilwa,mombasa,zanzibar,indian ocean,culture',
            'africa_score': 4.5
        }
    ]
    
    try:
        # Initialize the Flask app and database
        sys.path.insert(0, '.')
        from app import app, db, Content, text_processor
        
        with app.app_context():
            db.create_all()
            
            # Check if sample content already exists
            existing_count = Content.query.count()
            if existing_count > 0:
                print(f"✓ Database already contains {existing_count} content items")
                return True
            
            # Add sample content
            for item in sample_content:
                # Process content
                full_text = f"{item['title']} {item['content']}"
                processed_content = text_processor.preprocess_text(full_text)
                
                new_content = Content(
                    title=item['title'],
                    content=item['content'],
                    processed_content=processed_content,
                    keywords=item['keywords'],
                    africa_score=item['africa_score'],
                    created_at=datetime.utcnow()
                )
                
                db.session.add(new_content)
                print(f"✓ Added sample content: {item['title']}")
            
            db.session.commit()
            print(f"✓ Successfully added {len(sample_content)} sample content items")
            return True
            
    except Exception as e:
        print(f"Error adding sample content: {e}")
        return False

def create_env_file():
    """Create .env file if it doesn't exist"""
    if not os.path.exists('.env'):
        with open('.env', 'w') as f:
            f.write("""# Sankofa AI Environment Configuration
SECRET_KEY=sankofa-ai-development-key-change-in-production
FLASK_ENV=development
DATABASE_URL=sqlite:///africa_history.db
PORT=5000
MAX_CONTENT_LENGTH=16777216
UPLOAD_FOLDER=static/uploads
""")
        print("✓ Created .env file with default settings")
    else:
        print("✓ .env file already exists")

def test_application():
    """Basic test to ensure the application starts correctly"""
    try:
        sys.path.insert(0, '.')
        from app import app, search_engine
        
        with app.app_context():
            # Test search engine
            search_engine.index_content()
            results = search_engine.search("ancient egypt", limit=2)
            
            if results:
                print(f"✓ Search engine working - found {len(results)} results")
                print(f"  Top result: {results[0]['title']}")
            else:
                print("⚠ Search engine returned no results (normal if no content)")
        
        print("✓ Application components loaded successfully")
        return True
        
    except Exception as e:
        print(f"✗ Error testing application: {e}")
        return False

def main():
    """Main setup function"""
    print("🌍 Sankofa AI Setup Script")
    print("=" * 50)
    
    success = True
    
    print("\n1. Checking dependencies...")
    if not check_dependencies():
        success = False
    
    print("\n2. Creating directories...")
    create_directories()
    
    print("\n3. Setting up NLTK data...")
    if not setup_nltk():
        success = False
    
    print("\n4. Creating environment file...")
    create_env_file()
    
    print("\n5. Setting up database and sample content...")
    if not create_sample_content():
        success = False
    
    print("\n6. Testing application...")
    if not test_application():
        success = False
    
    print("\n" + "=" * 50)
    if success:
        print("✅ Setup completed successfully!")
        print("\nNext steps:")
        print("1. Add africa.png and nyame.png images to static/images/")
        print("2. Run the application: python app.py")
        print("3. Visit http://localhost:5000")
        print("4. Upload your own African history content")
        print("\nFor deployment, see the deployment guide in README.md")
    else:
        print("❌ Setup completed with errors!")
        print("Please fix the issues above before running the application.")
    
    return success

if __name__ == "__main__":
    main()