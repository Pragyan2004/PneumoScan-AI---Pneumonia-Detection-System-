import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
os.environ['TF_FORCE_GPU_ALLOW_GROWTH'] = 'true'

import matplotlib
matplotlib.use('Agg')

import tensorflow as tf
tf.config.threading.set_inter_op_parallelism_threads(1)
tf.config.threading.set_intra_op_parallelism_threads(1)

from flask import Flask, render_template, request, jsonify
import numpy as np
import pickle
from PIL import Image
import io
import base64
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import logging
import traceback

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'pneumoscan-ai-secret-key-2024'
app.config['UPLOAD_FOLDER'] = 'static/uploads/'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

model = None
model_info = None
model_loaded = False

def load_ai_model():
    """Load the trained pneumonia detection model"""
    global model, model_info, model_loaded
    try:
        logger.info("Loading AI model...")
        
        if not os.path.exists('pneumonia_detection_cnn.h5'):
            logger.error("Model file 'pneumonia_detection_cnn.h5' not found!")
            return
            
        if not os.path.exists('pneumonia_model_info.pkl'):
            logger.error("Model info file 'pneumonia_model_info.pkl' not found!")
            return
        
        model = tf.keras.models.load_model('pneumonia_detection_cnn.h5', compile=True)
        logger.info("✓ Model architecture loaded")
        
        with open('pneumonia_model_info.pkl', 'rb') as f:
            model_info = pickle.load(f)
            
        model_loaded = True
        logger.info("✓ AI Model loaded successfully")
        logger.info(f"Model input shape: {model.input_shape}")
        logger.info(f"Model output shape: {model.output_shape}")
        
    except Exception as e:
        logger.error(f"Error loading model: {e}")
        logger.error(traceback.format_exc())
        model = None
        model_info = None
        model_loaded = False

load_ai_model()

def preprocess_image(image_path, target_size=(150, 150)):
    """Preprocess image for model prediction"""
    try:
        logger.info(f"Preprocessing image: {image_path}")
        
        img = Image.open(image_path).convert('L')
        logger.info(f"Original image size: {img.size}, mode: {img.mode}")
        
        img = img.resize(target_size)
        img_array = np.array(img, dtype=np.float32) / 255.0
        logger.info(f"Processed image array shape: {img_array.shape}")
        
        img_array = img_array.reshape(1, target_size[0], target_size[1], 1)
        logger.info(f"Final input shape: {img_array.shape}")
        
        return img_array
        
    except Exception as e:
        logger.error(f"Error preprocessing image: {e}")
        logger.error(traceback.format_exc())
        return None

def predict_pneumonia(image_path):
    """Make prediction on the uploaded image"""
    if not model_loaded or model is None:
        logger.error("Model not loaded, cannot make prediction")
        return None, None, "Model not loaded properly"
    
    try:
        processed_image = preprocess_image(image_path)
        if processed_image is None:
            return None, None, "Image preprocessing failed"
        
        logger.info("Making prediction...")
        
        prediction = model.predict(processed_image, verbose=0)
        logger.info(f"Raw prediction output: {prediction}")
        
        prediction_value = prediction[0][0]
        logger.info(f"Prediction value: {prediction_value}")
        
        class_name = 'Pneumonia' if prediction_value > 0.5 else 'Normal'
        confidence = prediction_value if prediction_value > 0.5 else 1 - prediction_value
        
        logger.info(f"Result: {class_name} with {confidence:.3f} confidence")
        
        return class_name, float(confidence), "Success"
        
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        logger.error(traceback.format_exc())
        return None, None, str(e)

def create_confidence_chart(confidence):
    """Create a base64 encoded confidence chart"""
    try:
        plt.switch_backend('Agg')
        
        fig, ax = plt.subplots(figsize=(8, 2), dpi=100)
        colors = ['#ff6b6b', '#51cf66']
        
        ax.barh([0], [confidence * 100], color=colors[1], alpha=0.7)
        ax.barh([0], [(1 - confidence) * 100], left=[confidence * 100], color=colors[0], alpha=0.7)
        ax.set_xlim(0, 100)
        ax.set_yticks([])
        ax.set_xlabel('Confidence (%)', fontsize=10)
        ax.text(50, 0, f'{confidence*100:.1f}%', ha='center', va='center', 
                fontsize=14, fontweight='bold', color='white')
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', 
                   transparent=True, dpi=100, pad_inches=0.1)
        buf.seek(0)
        chart_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        plt.close(fig)
        buf.close()
        
        return chart_base64
    except Exception as e:
        logger.error(f"Chart creation error: {e}")
        return None

@app.route('/')
def index():
    return render_template('index.html', model_loaded=model_loaded)

@app.route('/upload')
def upload():
    return render_template('upload.html', model_loaded=model_loaded)

@app.route('/predict', methods=['POST'])
def predict():
    logger.info("Received prediction request")
    
    if 'file' not in request.files:
        logger.error("No file in request")
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        logger.error("Empty filename")
        return jsonify({'error': 'No file selected'}), 400
    
    if not model_loaded:
        logger.error("Model not loaded")
        return jsonify({'error': 'AI model not loaded properly. Please try again later.'}), 500
    
    try:
        allowed_extensions = {'.jpg', '.jpeg', '.png'}
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            logger.error(f"Invalid file type: {file_ext}")
            return jsonify({'error': f'File type {file_ext} not supported. Please use JPG or PNG files.'}), 400
        
        filename = datetime.now().strftime("%Y%m%d_%H%M%S_") + file.filename
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        logger.info(f"File saved to: {filepath}")
        
        if not os.path.exists(filepath):
            logger.error("File was not saved successfully")
            return jsonify({'error': 'Failed to save uploaded file'}), 500
            
        file_size = os.path.getsize(filepath)
        logger.info(f"Saved file size: {file_size} bytes")
        
        
        logger.info("Starting prediction...")
        class_name, confidence, status = predict_pneumonia(filepath)
        logger.info(f"Prediction result - Status: {status}, Class: {class_name}, Confidence: {confidence}")
        
        if status != "Success":
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({'error': status}), 500
        chart_base64 = create_confidence_chart(confidence)
        
        result = {
            'class_name': class_name,
            'confidence': round(confidence * 100, 2),
            'image_url': f'/static/uploads/{filename}',
            'chart': chart_base64,
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'model_loaded': model_loaded
        }
        
        logger.info("Prediction completed successfully")
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Prediction endpoint error: {e}")
        logger.error(traceback.format_exc())
        # Clean up file if error occurs
        if 'filepath' in locals() and os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/results')
def results():
    return render_template('results.html', model_loaded=model_loaded)

@app.route('/about')
def about():
    return render_template('about.html', model_loaded=model_loaded)

@app.route('/statistics')
def statistics():
    stats_data = {
        'total_scans': 12543,
        'pneumonia_cases': 3247,
        'normal_cases': 9296,
        'accuracy': 94.2,
        'precision': 92.8,
        'recall': 95.1,
        'model_loaded': model_loaded
    }
    return render_template('statistics.html', stats=stats_data)

@app.route('/contact')
def contact():
    return render_template('contact.html', model_loaded=model_loaded)

@app.route('/api/model-info')
def api_model_info():
    if not model_loaded or model_info is None:
        return jsonify({'error': 'Model info not available'}), 500
    
    return jsonify({
        'input_shape': model_info.get('input_shape'),
        'class_names': model_info.get('class_names'),
        'test_metrics': model_info.get('test_metrics'),
        'model_loaded': model_loaded
    })

@app.route('/api/health')
def api_health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy' if model_loaded else 'degraded',
        'model_loaded': model_loaded,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/debug')
def api_debug():
    """Debug endpoint to check model status"""
    model_status = {
        'model_loaded': model_loaded,
        'model_exists': model is not None,
        'model_info_exists': model_info is not None,
        'upload_folder_exists': os.path.exists(app.config['UPLOAD_FOLDER']),
        'upload_folder': app.config['UPLOAD_FOLDER']
    }
    
    if model_loaded:
        model_status.update({
            'input_shape': str(model.input_shape),
            'output_shape': str(model.output_shape)
        })
    
    return jsonify(model_status)

if __name__ == '__main__':
    logger.info("Starting PneumoScan AI Flask application...")
    logger.info(f"Model loaded: {model_loaded}")
    
    app.run(
        debug=True, 
        host='0.0.0.0', 
        port=5000,
        threaded=False
    )