import pytest
import json
import os
from flask import Flask
from backend.routes import api_blueprint
from backend.config_manager import save_config

@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(api_blueprint, url_prefix='/api')
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_config(client):
    # Test GET config
    rv = client.get('/api/config')
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert 'api_key' in data

    # Test POST config
    new_config = data.copy()
    new_config['MAX_WORKERS'] = 5
    rv = client.post('/api/config', json=new_config)
    assert rv.status_code == 200
    
    rv = client.get('/api/config')
    data = json.loads(rv.data)
    assert data['MAX_WORKERS'] == 5

def test_check_folder(client, tmp_path):
    # Create dummy files
    d = tmp_path / "test_data"
    d.mkdir()
    (d / "glossary.xlsx").touch()
    (d / "ref.txt").touch()
    
    rv = client.post('/api/check-folder', json={'path': str(d)})
    data = json.loads(rv.data)
    assert data['valid'] == True
    
    rv = client.post('/api/check-folder', json={'path': str(d / "nonexistent")})
    data = json.loads(rv.data)
    assert data['valid'] == False

def test_status(client):
    rv = client.get('/api/status')
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert 'running' in data
    assert 'progress' in data
