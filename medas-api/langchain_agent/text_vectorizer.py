import numpy as np
from openai import OpenAI


class TextVectorizer:
    def __init__(self, api_key=None):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )

    def vectorize(self, text):
        """
        Convert input text into a vector using an embedding model via OpenRouter.

        :param text: Input text to vectorize
        :return: Numpy array of the text embedding
        """
        try:
            # Request embedding via OpenRouter
            response = self.client.embeddings.create(input=text, model=self.model)

            # Extract the embedding vector
            embedding = response.data[0].embedding
            return np.array(embedding)

        except Exception as e:
            print(f"Error during vectorization: {e}")
            return None
