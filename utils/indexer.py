import pickle
from typing import List
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor
from scipy.spatial.distance import cdist
from sklearn.cluster import KMeans
from utils.config import DB_CONFIG

# IVF index parameters
N_CLUSTERS = 1
N_PROBE = 5
TOP_K = 5

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def fetch_vectors(table_name: str, vector_column: str):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute(f"""
        SELECT samples.subject_id, {table_name}.{vector_column}
        FROM {table_name}
        JOIN samples ON {table_name}.sample_id = samples.sample_id
        WHERE samples.status = 'active' AND {table_name}.{vector_column} IS NOT NULL
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    subject_ids = []
    vectors = []
    for row in rows:
        sid = row['subject_id']
        vec_list = row[vector_column]
        arr = np.array(vec_list, dtype=np.float32)
        subject_ids.append(sid)
        vectors.append(arr)

    if not vectors:
        return [], np.zeros((0, 0), dtype=np.float32)

    vectors_np = np.stack(vectors, axis=0)
    return subject_ids, vectors_np


class IVFIndex:
    def __init__(self, n_clusters: int = 100, n_probe: int = 5, top_k: int = 5):
        self.n_clusters = n_clusters
        self.n_probe = n_probe
        self.top_k = top_k

        self.kmeans = None
        self.inverted_lists = {}
        self.sample_ids = None
        self.vectors = None

    def fit(self, ids: List[int], vectors: np.ndarray):
        if len(ids) == 0:
            raise ValueError("No vectors provided for training.")

        self.sample_ids = ids
        self.vectors = vectors

        self.kmeans = KMeans(n_clusters=self.n_clusters, random_state=0)
        self.kmeans.fit(vectors)
        labels = self.kmeans.labels_

        self.inverted_lists = {i: [] for i in range(self.n_clusters)}
        for idx, label in enumerate(labels):
            sid = ids[idx]
            vec = vectors[idx]
            self.inverted_lists[label].append((sid, vec))

    def search(self, query_vector: np.ndarray):
        if self.kmeans is None:
            raise ValueError("Index not trained. Call fit() first.")
        print('vector:', query_vector)
        print('vector dimensions:', query_vector.shape)
        q = query_vector.reshape(1, -1)
        print('index dimensions:', self.kmeans.cluster_centers_.shape)
        centroid_dists = cdist(q, self.kmeans.cluster_centers_, metric='cosine')[0]
        closest_clusters = np.argsort(centroid_dists)[:self.n_probe]

        candidates = []
        for cluster_id in closest_clusters:
            candidates.extend(self.inverted_lists.get(cluster_id, []))

        if not candidates:
            return []

        cands_vecs = np.array([vec for (_, vec) in candidates])
        cands_ids = [sid for (sid, _) in candidates]
        dists = cdist(q, cands_vecs, metric='cosine')[0]

        nearest_idx = np.argsort(dists)[:self.top_k]
        results = [(cands_ids[i], float(dists[i])) for i in nearest_idx]
        #print(results)
        return results

    def save(self, filepath: str):
        with open(filepath, 'wb') as f:
            pickle.dump({
                'n_clusters': self.n_clusters,
                'n_probe': self.n_probe,
                'top_k': self.top_k,
                'kmeans': self.kmeans,
                'inverted_lists': self.inverted_lists,
                'sample_ids': self.sample_ids,
                'vectors': self.vectors
            }, f)

    @classmethod
    def load(cls, filepath: str):
        with open(filepath, 'rb') as f:
            data = pickle.load(f)
        obj = cls(n_clusters=data['n_clusters'], n_probe=data['n_probe'], top_k=data['top_k'])
        obj.kmeans = data['kmeans']
        obj.inverted_lists = data['inverted_lists']
        obj.sample_ids = data['sample_ids']
        obj.vectors = data['vectors']
        return obj

def update_index(table_name, vector_column, index_path):
    print(f"Обновление индекса для {table_name}.{vector_column}...")
    ids, vectors = fetch_vectors(table_name, vector_column)
    index = IVFIndex(n_clusters=N_CLUSTERS, n_probe=N_PROBE, top_k=TOP_K)
    index.fit(ids, vectors)
    index.save(index_path)
    print("Индекс успешно обновлен")

def load_index_and_search(index_path: str, query_vector: np.ndarray):
    print(f"Загрузка индекса из {index_path}...")
    index = IVFIndex.load(index_path)
    print("Индекс загружен")
    return index.search(query_vector)


if __name__ == "__main__":
    face_index_file = "face_ivf_index.pkl"
    update_index(table_name="face_samples", vector_column="feature_vector", index_path=face_index_file)

    """Example usage for other modalities:
    
    # Voice modality
    voice_index_file = "voice_ivf_index.pkl"
    update_index("voice_samples", "audio_vector", voice_index_file)

    # Signature modality
    signature_index_file = "signature_ivf_index.pkl"
    update_index("signature_samples", "signature_vector", signature_index_file)

    # Search example (assuming we have a query vector)
    # query_vec = fu.get_face_vector("tmp_face_login.png")
    # results = load_index_and_search(face_index_file, np.array(query_vec))
    # print("Search results:", results)
    """