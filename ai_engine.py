import streamlit as st
from openai import OpenAI

class AIEngine:
    def __init__(self):
        #self.openai_key = st.secrets.get("OPENAI_API_KEY", None)
        #self.grok_key = st.secrets.get("GROK_API_KEY", None)
        self.grok_key = st.secrets.get("groq", {}).get("key")
        self.openai_key = st.secrets.get("openai", {}).get("key")

        self.active_model = None
        
        # OpenAI client (defaults to OpenAI endpoint)
        self.openai_client = OpenAI(api_key=self.openai_key) if self.openai_key else None
        
        # Grok client (OpenAI SDK with xAI base URL)
        self.grok_client = Groq(api_key=self.grok_key) if self.grok_key else None
        
        

    def test_connection(self):
        results = {}
        
        # Test OpenAI
        if self.openai_client:
            try:
                # Use a lightweight test instead of full models.list() for speed
                self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": "test"}],
                    max_tokens=1
                )
                results["openai"] = True
            except Exception:
                results["openai"] = False
        else:
            results["openai"] = False
        
        # Test Grok
        if self.grok_client:
            try:
                self.grok_client.chat.completions.create(
                    model="grok-4-0709",  # Current model; adjust if needed
                    messages=[{"role": "user", "content": "test"}],
                    max_tokens=1
                )
                results["grok"] = True
            except Exception:
                results["grok"] = False
        else:
            results["grok"] = False
        
        return results

    def generate(self, prompt: str):
        # --- Try OpenAI first ---
        if self.openai_client:
            try:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}]
                )
                self.active_model = "OpenAI GPT-4o-mini"
                return response.choices[0].message.content
            except Exception as e:
                st.warning(f"⚠️ OpenAI failed, switching to Grok ({e})")
    
        # --- Fallback to Grok ---
        if self.grok_client:
            try:
                response = self.grok_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": prompt}]
                )
                self.active_model = "xAI Grok-4-0709"
                return response.choices[0].message.content
            except Exception as e:
                # Return subtle message only if both failed
                return "❌ Both OpenAI and Grok failed. Check your API keys."
    
        return "❌ No valid AI model available. Please configure API keys."




