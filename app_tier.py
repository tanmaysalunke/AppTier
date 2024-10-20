import boto3
import json
import base64
import os
import tempfile
import subprocess
import time

# AWS Setup
ASU_ID = '1229850390'
input_bucket_name = f'{ASU_ID}-in-bucket'
output_bucket_name = f'{ASU_ID}-out-bucket'
sqs = boto3.client('sqs', region_name='us-east-1')
request_queue_url = f'https://sqs.us-west-2.amazonaws.com/442042549532/{ASU_ID}-req-queue'
response_queue_url = f'https://sqs.us-west-2.amazonaws.com/442042549532/{ASU_ID}-resp-queue'
s3 = boto3.client('s3')

def upload_image_to_s3(bucket_name, file_name, image_data):
    # Ensure the file name has the correct extension
    if not file_name.endswith('.jpg'):
        file_name += '.jpg'
        
    decoded_image = base64.b64decode(image_data)
    s3.put_object(Bucket=bucket_name, Key=file_name, Body=decoded_image, ContentType='image/jpeg')
    print(f"Uploaded {file_name} to S3 input bucket {bucket_name}")


def upload_classification_to_s3(bucket_name, file_name, classification_result):
    s3.put_object(Bucket=bucket_name, Key=file_name, Body=classification_result)
    print(f"Uploaded {file_name} to S3 output bucket {bucket_name}")

def process_image(image_data):
    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
        temp_file.write(base64.b64decode(image_data))
        temp_file_path = temp_file.name

    # Calling face_recognition.py as a subprocess
    process = subprocess.run(['python', 'face_recognition.py', temp_file_path], capture_output=True, text=True)
    os.unlink(temp_file_path)  # Clean up the temporary file

    if process.returncode == 0:
        return process.stdout.strip()
    else:
        raise Exception(f"Error in face recognition: {process.stderr}")

def poll_sqs():
    while True:
        response = sqs.receive_message(QueueUrl=request_queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=20)
        if 'Messages' in response:
            for message in response['Messages']:
                receipt_handle = message['ReceiptHandle']
                body = json.loads(message['Body'])
                file_name = body['fileName']
                file_content = body['fileContent']

                print(f"Processing image: {file_name}")
                person_name = process_image(file_content)
                if person_name:
                    upload_image_to_s3(input_bucket_name, file_name, file_content)
                    upload_classification_to_s3(output_bucket_name, file_name.split('.')[0], person_name)
                    sqs.send_message(QueueUrl=response_queue_url, MessageBody=json.dumps({'fileName': file_name, 'classificationResult': person_name}))
                    sqs.delete_message(QueueUrl=request_queue_url, ReceiptHandle=receipt_handle)
                    print(f"Processed {file_name}: {person_name}")
        else:
            print("No messages in the queue. Waiting...")
            time.sleep(5)

if __name__ == "__main__":
    print("Starting the App Tier instance...")
    poll_sqs()
