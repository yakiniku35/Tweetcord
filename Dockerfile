# Dockerfile

# ... previous content of Dockerfile

# Install requirements
RUN pip install -r requirements.txt

# Add pip install for tweety
RUN pip install --no-cache-dir --upgrade --force-reinstall git+https://github.com/mahrtayyab/tweety.git