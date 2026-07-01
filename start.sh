python3 -m venv venv

source venv/bin/activate

sudo apt-get update && sudo apt-get install -y \
    ffmpeg \
    espeak-ng \
    espeak-ng-data \
    imagemagick
    
python -m playwright install --with-deps

pip install -r r.txt
