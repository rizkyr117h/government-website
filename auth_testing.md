# Auth Testing Playbook — Kabar Buruk

## Step 1: MongoDB Verification
```
mongosh
use test_database
db.users.find({role: "admin"}).pretty()
db.users.findOne({role: "admin"}, {password_hash: 1})
```
Verify: bcrypt hash starts with `$2b$`, indexes exist on users.email (unique), login_attempts.identifier.

## Step 2: API Testing
```
API_URL=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2)
curl -c cookies.txt -X POST $API_URL/api/auth/login -H "Content-Type: application/json" -d '{"email":"admin@kaburburuk.id","password":"admin123"}'
cat cookies.txt
curl -b cookies.txt $API_URL/api/auth/me
```
Login should return the user object and set `access_token` + `refresh_token` cookies. The `/me` call should return the same user using those cookies.

## Step 3: Brute force
5 failed logins on the same email+IP => 429 "Terlalu banyak percobaan" for 15 min.
