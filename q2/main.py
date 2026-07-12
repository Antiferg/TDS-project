from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import base64
import tempfile
import ollama

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ImageRequest(BaseModel):
    image_base64: str
    question: str


@app.post("/answer-image")
async def answer_image(req: ImageRequest):
    img_bytes = base64.b64decode(req.image_base64)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(img_bytes)
        image_path = f.name

    response = ollama.chat(
        model="gemma3:4b",
        messages=[
            {
                "role": "user",
                "content": (
                    "Answer ONLY the question. "
                    "If the answer is numeric, return only the number without units or symbols."
                    f"\nQuestion: {req.question}"
                ),
                "images": [image_path],
            }
        ],
    )

    return {
        "answer": response["message"]["content"].strip()
    }
