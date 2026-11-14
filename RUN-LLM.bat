@echo off
cd /d "%~dp0"
echo ============================================
echo   Investor Intelligence Engine - LLM Run
echo ============================================
echo.
echo Free key yahan se milti hai: https://aistudio.google.com/apikey
echo (key kahin save nahi hogi - sirf is run ke liye use hogi)
echo.
set /p GEMINI_API_KEY=Apni Gemini API key paste karo aur Enter dabao:
echo.
echo --- LLM scoring: 60 investors (30 analyst picks + 30 others), ~10-12 min ---
echo Free tier ki daily limit lag gayi to koi baat nahi: kal yahi file dobara chalao,
echo jo ho chuka hai wo cache se aayega aur run wahin se aage badhega.
echo.
python src/scoring.py --mode llm --sample 60
if errorlevel 1 (
    echo.
    echo Kuch galat hua - upar wala error message Claude ko paste kar dena.
    pause
    exit /b 1
)
echo.
echo --- LLM vs rubric comparison ---
python src/compare.py
echo.
set /p DRAFTS=Top-10 investors ke liye LLM outreach drafts bhi banayein? (Y/N):
if /i "%DRAFTS%"=="Y" python src/outreach.py --top 10 --mode llm
echo.
echo Done! Upar ke numbers Claude ko bata dena. Dashboard: streamlit run app.py
pause
