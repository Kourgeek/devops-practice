FROM jenkins/jenkins:lts-jdk17

# Install base utilities
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    openssh-client \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

USER jenkins

EXPOSE 8080 50000
