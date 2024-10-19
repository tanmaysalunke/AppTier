import boto3
import json
import torch
import sys
from PIL import Image
import base64
import io
import time
from facenet_pytorch import MTCNN, InceptionResnetV1
import torch
import os

# S3 Bucket Names
ASU_ID = '1229850390'  # Replace with your ASU ID
input_bucket_name = f'{ASU_ID}-in-bucket'
output_bucket_name = f'{ASU_ID}-out-bucket'

# Face recognition initialization from face_recognition.py
mtcnn = MTCNN(image_size=240, margin=0, min_face_size=20)  # Face detection
resnet = InceptionResnetV1(pretrained='vggface2').eval()  # Embedding conversion

# SQS Queue URLs
sqs = boto3.client('sqs', region_name='us-east-1')
request_queue_url = 'https://sqs.us-west-2.amazonaws.com/442042549532/1229850390-req-queue'
response_queue_url = 'https://sqs.us-west-2.amazonaws.com/442042549532/1229850390-resp-queue'

# Initialize S3 client
s3 = boto3.client('s3')

def face_match(img, data_path): 
    """
    Performs face matching using the pre-trained model and saved embeddings.
    img: PIL image
    data_path: Path to the saved embeddings (.pt file)
    """
    # Getting embedding matrix of the given img
    face, prob = mtcnn(img, return_prob=True)  # Returns cropped face and probability
    emb = resnet(face.unsqueeze(0)).detach()  # Get embedding for the image

    # Load saved embeddings and names
    saved_data = torch.load(data_path)  # loading data.pt file
    embedding_list = saved_data[0]  # Getting embedding data
    name_list = saved_data[1]  # Getting list of names
    dist_list = []  # List of matched distances, minimum distance identifies the person

    for idx, emb_db in enumerate(embedding_list):
        dist = torch.dist(emb, emb_db).item()
        dist_list.append(dist)

    idx_min = dist_list.index(min(dist_list))
    return (name_list[idx_min], min(dist_list))

def upload_image_to_s3(bucket_name, file_name, image_data):
    """
    Uploads the original image to the specified S3 input bucket.
    """
    # Decode the base64 image data back to binary
    decoded_image = base64.b64decode(image_data)

    # Upload the image in binary format to the input S3 bucket
    s3.put_object(Bucket=bucket_name, Key=file_name, Body=decoded_image)
    print(f"Uploaded {file_name} to S3 input bucket {bucket_name}")

def download_image_from_s3(bucket_name, file_name):
    """
    Downloads an image file from the specified S3 bucket.
    Returns the image content in base64-encoded format.
    """
    obj = s3.get_object(Bucket=bucket_name, Key=file_name)
    return obj['Body'].read()

def upload_classification_to_s3(bucket_name, file_name, classification_result):
    """
    Uploads the classification result to the specified S3 bucket.
    """
    s3.put_object(Bucket=bucket_name, Key=file_name, Body=classification_result)

def process_image(image_data):
    """
    This function takes in base64-encoded image data, processes it, and returns the
    face recognition result using the face_match function from face_recognition.py.
    """
    # Decode the base64 image data
    img = Image.open(io.BytesIO(base64.b64decode(image_data)))

    # Perform face recognition using the model and return the result
    return face_match(img, 'data.pt')

def process_image(image_data):
    """
    This function takes in base64-encoded image data, processes it, and returns the
    face recognition result using the face_match function from face_recognition.py.
    """
    # Decode the base64 image data
    img = Image.open(io.BytesIO(base64.b64decode(image_data)))

    # Perform face recognition using the model and return the result
    return face_match(img, 'data.pt')

def poll_sqs():
    """
    Poll the SQS request queue for image processing jobs and send the results
    back to the response queue.
    """
    while True:
        # Receive messages from the Request Queue
        response = sqs.receive_message(
            QueueUrl=request_queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20  # Enable long polling
        )

        # Check if messages are available
        if 'Messages' in response:
            for message in response['Messages']:
                receipt_handle = message['ReceiptHandle']

                # Parse the message body (contains fileName and fileContent)
                body = json.loads(message['Body'])
                file_name = body['fileName']
                file_content = body['fileContent']  # Base64-encoded image content

                print(f"Processing image: {file_name}")

                # Upload the original image to S3 input bucket
                upload_image_to_s3(input_bucket_name, file_name, file_content)

                # Process the image using the face recognition model
                person_name, confidence = process_image(file_content)

                # Upload the classification result to S3 output bucket
                result_file_name = file_name.split('.')[0]  # Removing extension for result file
                classification_result = f"{person_name}"
                upload_classification_to_s3(output_bucket_name, result_file_name, classification_result)

                # Send the result to the Response Queue
                sqs.send_message(
                    QueueUrl=response_queue_url,
                    MessageBody=json.dumps({
                        'fileName': file_name,
                        'classificationResult': person_name
                    })
                )

                # Delete the processed message from the Request Queue
                sqs.delete_message(
                    QueueUrl=request_queue_url,
                    ReceiptHandle=receipt_handle
                )

                print(f"Processed {file_name}: {person_name}")
        else:
            print("No messages in the queue. Waiting...")
            time.sleep(5)

# Function to get the current length of the SQS queue
def get_queue_length():
    response = sqs.get_queue_attributes(
        QueueUrl=request_queue_url,
        AttributeNames=['ApproximateNumberOfMessages']
    )
    return int(response['Attributes']['ApproximateNumberOfMessages'])

# Run auto-scaling and message polling together
if __name__ == "__main__":
    print("Starting the App Tier instance...")
    
    # Run auto-scaling every 60 seconds in the background
    while True:
        poll_sqs()  # This handles message processing from SQS
        time.sleep(60)
