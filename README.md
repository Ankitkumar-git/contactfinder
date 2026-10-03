# Contact Finder

Search a company in your Apollo account, pick a team, and download a CSV of names, titles, emails, phones, and LinkedIn profile links.

This app does not log into LinkedIn. Profile links come from Apollo enrichment.

## Setup

1. Create a master API key in Apollo: [Create API keys](https://docs.apollo.io/docs/create-api-key).
2. From this folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

3. Open http://127.0.0.1:8000
4. Paste the API key into the page and save it. It is stored in `data/settings.json` on this computer and is not committed.

You can also put the key in a `.env` file copied from `.env.example`. A key saved in the app takes priority.

## Search

1. Search the company name and pick the right match.
2. Choose a team, or type extra job titles.
3. Choose Email, Phone, or Both. The default result cap is 25 people, and the maximum is 100.
4. Click **Find contacts**. Enrichment spends Apollo credits.
5. Download the CSV. Columns are name, designation, email, phone, linkedin_url, company, domain, location, and seniority.

Phone numbers are delivered by Apollo a few minutes after the first response. The page waits and fills them in. Work email is requested; personal email is not.

Keep the server on `127.0.0.1`. The API key is meant for this machine only.
