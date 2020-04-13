import speech_recognition as sr  

# get audio from the microphone                                                                       
r = sr.Recognizer()
f = "http://localhost:3000/5bb83438-c799-47e0-ae3c-0181c02330de"

with sr.Microphone() as source:                                                                       
    print("Speak:")                                                                                   
    audio = r.listen(source) 
    print(audio)  

try:
    print("You said " + r.recognize_google(audio))
except sr.UnknownValueError:
    print("Could not understand audio")
except sr.RequestError as e:
    print("Could not request results; {0}".format(e))
