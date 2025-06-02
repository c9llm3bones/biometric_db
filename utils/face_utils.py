import face_recognition

def extract_face_vector(image_path):
    print("loading image:", image_path)
    try:
        image = face_recognition.load_image_file(image_path)
        face_locations = face_recognition.face_locations(image)
        if not face_locations:
            return None

        face_vector = face_recognition.face_encodings(image, face_locations)[0]
        return face_vector.tolist()
    except Exception as e:
        print("Ошибка при векторизации:", e)
        return None

#print(extract_face_vector('/home/kostya/biometric_course_work/dataset/faces/Authorize/Ira2.jpg'))