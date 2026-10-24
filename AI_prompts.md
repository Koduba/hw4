# HW4 — AI Prompts Log

## Problem 1: Vibe coder prompts

### Prompt 1

> go ahead and create the AI_prompts.md log like w e did for the last hw

### Prompt 2

> good, you knwo the rules so follow them like we did before

*What was lacking in Prompt 1:* it created the log file but did not say that the same logging and workspace rules from the last homework should be followed going forward.

## Problem 2: Analyze the database

### Prompt 1

> look at the datsbase and give me a report. you should at the miniu understand the catalogue, invetory and users

### Prompt 2

> ok good, start a harness.md file.write each table and its feild , one short line on why each matters for the shop or chatbot we will be creating. note that this file will continue to gow as we go along.

*What was lacking in Prompt 1:* it asked for a one-off report but not a lasting, field-by-field reference explaining why each column matters for the shop and chatbot.

## Problem 3: Build the Campus Customs website

### Prompt 1

> Scaffold  react + vite+ typescript front end for the site. put a nav bar at the top that links to home, products, about us, log in and create account. Pull customs style  wording from yalebulldogblue.com for home and about us but write in your own voice. do not copy original site text.

### Prompt 2

> on the products page  show product images and add basic peroduct info. use the info from the database. make each product have its own unique page, clicking a card on the product page should take the user to item page. Add a chat feature at the bottom right. no need to talk to an agent yet, a stub that will connect to a backend is going to be used. you will sopn need an api to read the database so start a small fast API app in. backend/main.py just to serve products and images then grow it into the agent backend in problem 5.

*What was lacking in Prompt 1:* it set up the site's shell and pages but did not ask for real catalogue data, product detail pages, a chat widget, or a backend API to serve the database.

## Problem 4: Create account and login

### Prompt 1

> Build a normal login and create avccount flow. include confieming padssword too. create a users table if not existing yet to save new accounts. be sure to add security features such that AI nor hackers can stael info or access data.

### Prompt 2

> The seed database already has a test user you can use while building:
> Email: test@campuscustoms.yale.edu
>
> * Password: password
> * Hash function: PBKDF2-HMAC-SHA256, 120,000 iterations (stored as
> pbkdf2_sha256$salt$hash)
>
> How login checks a password:
>
> * You never un-hash the stored value. You re-hash what the user typed and compare.
> * Read the salt out of the stored string (the middle piece) - do not make a new one at login.
> * Hash the typed password with that same salt, then compare to the stored hash. Use a constant-time compare.
> * Signup and login must use the same hash settings (same function, same salt handling, same iteration count). If they differ, even the right password will not match.
> * Surest check: log in as the seeded test user and as a brand-new account you just created in your own app.
>
> Confirm you can log in as that user, and that a brand-new account you create also works.
>
> Update output/harness.nd d with how auth works (what you store for a user and how passwords are protected).

*What was lacking in Prompt 1:* it didn't give the seed database's hashing settings (PBKDF2-SHA256, 120,000 iterations, `pbkdf2_sha256$salt$hash`) or ask for proof that both the seeded user and a new account can log in.

## Problem 5: Pydantic AI agent backend

### Prompt 1

> Build the shop chatbot as a PydanticAl agent behind FastAPl, plugged into your front-end chat widget. Put the API app in backend/main.py - that is the file you run with Uvicorn.
> Keep the agent as these four files next to it (same idea as Homework 3):
>
> * backend/prompts/prompt.md : system prompt (grow this same file later)
> * backend/agent.py: agent entry / wiring
> * backend/tools.py: tools the agent can call
> * backend/models.py: Pydantic / PydanticAl structured types
>
> In main.py , expose a chat route so a message from the website returns a reply from the agent (and whatever else you need for products/auth). You will need your Al model API key for the agent.

### Prompt 2

> Put Campus Customs voice and safety basics into prompts/prompt.md (you will expand tools and safety later). Start or update types in models. py for chat replies / product cards as needed.
> In output/harness.md, note how the front end talks to FastAPl and how the agent is loaded (prompt file + model).
>
> Make sure the backend runs from the backend/folder like this: uvicorn main:app --reload --port 8000

*What was lacking in Prompt 1:* it didn't specify the exact run command (`uvicorn main:app --reload --port 8000` from `backend/`), a dedicated product-card type for chat replies, or documentation of how the front end reaches FastAPI and how the agent loads its prompt and model.

## Problem 6: Tools: product info and stock

### Prompt 1

> Give the agent tools that look up real information from campus_customs.db:
>
> * Product description
> * Price
> * How many are in stock (by size when the customer asks)
>
> The agent must use the database, it should not invent prices or quantities. If a size is out of stock, say so clearly

### Prompt 2

> Expand prompts/prompt.md so the agent knows to call these tools for price and stock
> questions. Add or update return types in models.py .
> in output/harness.md, list each tool and explain which model fields you chose for lookup results and why.

*What was lacking in Prompt 1:* it asked for the tools themselves but not for explicit prompt guidance on when to call each one, or for a documented rationale behind the return-type fields.

## Problem 7: Chat search that updates the page

### Prompt 1

> lets add a nice feature to the site. When a customer asks about a type of item e.g. "what hoodies do you have?" the agent should search the catalogue and the website should dynamically show those matching items as product cards (image, name, price, short info).
> This is an API contract: the agent returns structured product matches and then the front end renders them on the website. let it be very cool

### Prompt 2

> After the dynamic product cards are loaded by your new feature, make sure the same single item page behavior you built in Problem 3 still works: each product card including the ones the chat just put on the page should all still open that detail view ( image and  info) when clicked.
> Update prompts/prompt.md and output/harness.md so it is clear how search results reach the page.

*What was lacking in Prompt 1:* it defined the showcase cards but didn't require that clicking them (and every other card) still opens the Problem 3 product detail page, or ask for documentation of the full search-to-page path.

## Problem 8: Customer memory

### Prompt 1

> When a shopper is logged in, save their chat history in the database in an appropriate table and reload it when they return. The agent should know who is chatting (name, email) put that in agent deps (or an equivalent clear pattern) and/or tools the agent can call.
>
> Also pass enough page context that if someone is on a product page and asks "do you have this in pink?", the agent knows which item they mean. Hint: you can put code into the agent context.
>
> Guests can still chat, but history only needs to persist for logged-in users.
> Document in output/harness.md: how user chat history is stored, what customer fields the agent sees, and how page context is passed.

## Problem 9: Usability improvements

### Prompt 1

> Now that the core shop works, improve it. Choose and implement:
>
> * 2 front-end usability improvements
> * 2 agent / backend usability improvements
>
> Front-end improvements are things that make the site look better and make it easier to use.
> Agent / backend improvements are things that make the agent output better, more accurate, or safer. These could be new agent tools or things that make the agent run faster or cheaper.
>
> Write output/usability.md before or as you build. For each of the improvements, say what you added and how it helps a Campus Customs shopper or the business
> Then make sure all improvements actually show up in the running app. Graders will read the write up and look for the features.

## Problem 10: Style the website

### Prompt 1

> Add creatively nice design so the site feels like a real Campus Customs storefront by improving fonts, color, hierarchy, motion, product presentation, chat feel. make it very imaginative and innovative in design, look and feel.
>
> Write output/design.md: what you changed and why it should help customers stick
> around and buy. Keep it short and sweet

### Prompt 2

> i would like us to human mockups and models of the products

*What was lacking in Prompt 1:* it restyled the site but still showed every product only as a flat product photo, with no images of real people wearing the clothes.

### Prompt 3

> the website should be in yale colors, change the enture theme from pink to yale blue

*What was lacking in Prompt 2:* it asked for on-model product images but kept the house black-and-pink palette instead of Yale's own colours.

## Problem 11: Site testing (app check)

### Prompt 1

> Test the live site and document it in output/app_check.html (a page i can double-click open). Include clear screenshots and short captions for:
>
> 1. Chat checking the inventory level of an item (honest stock/price from the DB)
> 2. The dynamic search-result cards appearing after a category question (e.g. hoodies)
> 3. One of the usability features you added in Problem 9
>
> Make the HTML easy to grade: heading for each check, screenshot, one or two sentences on what the screenshot proves. Put the screenshot image files in output/app_check_images/ and link them from app_check.html with relative paths (for example app_check_images/inventory.png

## Problem 12: Audit trail, safety, finish harness

### Prompt 1

> Keep an append only output/audit_trail.json of agent loop activity (time, tool name, short args/result, stop reason). Do not wipe it between runs. Also, think of some safety rules to give the agent and put them in prompts/prompt.nd
>
> Finish output/harness-nd so it is clear how the system works.
>
> * Model fields in models.py and why you chose them
> * Tools and abilities
> * Safety rulesSpecs (loop limits, result caps, models, how to run front + back)

## Problem 13: Push to GitHub and submit the URL

### Prompt 1

> Lets push this code in a folder named hw4 and push it to a public GitHub repository. do not push the envcampus_customs.db, or product images in the GitHub repo.
> Use.gitionore. Include. env. example with placeholders only.
>
> use the attached image as a templete for the correct file format

*(Attached template: `hw4/` containing `AI_prompts.md`, `requirements.txt`, `.env.example`, `.gitignore`, `README.md`, `frontend/` (Vite React TypeScript app), `backend/` (`main.py`, `agent.py`, `models.py`, `tools.py`, `prompts/prompt.md`) and `output/` (`harness.md`, `design.md`, `usability.md`, `app_check.html`, `app_check_images/`, `audit_trail.json`).)*
