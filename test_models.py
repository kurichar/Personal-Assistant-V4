from langchain_ollama import ChatOllama
from dotenv import load_dotenv
load_dotenv()

llm = ChatOllama(model="qwen3:latest", temperature=0)
print(llm.invoke("Say hi in 5 words.").content)
