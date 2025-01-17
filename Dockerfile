# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables for AWS credentials
ENV AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
ENV AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
ENV AWS_REGION=${AWS_REGION}

# Set the working directory inside the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --upgrade pip && \
    pip install boto3 requests

# Install PyTorch, TorchVision, and Torchaudio for CPU
RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu 

# Expose port 5000 (if necessary for the app to communicate)
EXPOSE 5000

# Run the app when the container launches
CMD ["python", "-u", "app_tier.py"]
