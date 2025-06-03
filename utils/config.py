DB_CONFIG = {
    "dbname": "biometrics_db",
    "user": "postgres",       
    "password": "123456", 
    "host": "localhost"
}

THRESHOLD_FACE = 0.06 # -> 0, при "Схожесть" -> inf
THRESHOLD_VOICE = 0.25 # -> 0, при "Схожесть" -> inf
THRESHOLD_SIGNATURE = 0.1 # -> 0, при "Схожесть" -> inf

BIOMETRIC_CONFIG = {
    'face': {
        'index_file': 'face_ivf_index.pkl',
        'samples_table': 'face_samples',
        'vector_column': 'feature_vector',
        'threshold': THRESHOLD_FACE,
        #'save_function': save_face_vector,
        'update_query': """
            UPDATE {table} SET {vector_column} = %s 
            WHERE sample_id = %s
        """
    },
    'voice': {
        'index_file': 'voice_ivf_index.pkl',
        'samples_table': 'voice_samples',
        'vector_column': 'audio_vector',
        'threshold': THRESHOLD_VOICE,
        #'save_function': save_voice_vector,
        'update_query': """
            UPDATE {table} SET {vector_column} = %s 
            WHERE sample_id = %s
        """
    },
    'signature': {
        'index_file': 'signature_ivf_index.pkl',
        'samples_table': 'signature_samples',
        'vector_column': 'signature_vector',
        'threshold': THRESHOLD_SIGNATURE,
        #'save_function': save_signature_vector,
        'update_query': """
            UPDATE {table} SET {vector_column} = %s 
            WHERE sample_id = %s
        """
    }
}
