# def test_full_admin_flow(client):
#     # 1) Login admin (default admin from settings)
#     res = client.post("/auth/admin/login", json={
#         "username": "admin",
#         "password": "admin"
#     })
#     assert res.status_code == 200
#     token = res.json()["access_token"]
#     headers = {"Authorization": f"Bearer {token}"}

#     # 2) Create another admin
#     res = client.post("/admins", json={
#         "username": "bob",
#         "password": "secure"
#     }, headers=headers)
#     assert res.status_code == 201

#     # 3) Create discount code
#     res = client.post("/admin/discount-codes", headers=headers)
#     assert res.status_code == 201
#     code = res.json()["code"]
#     assert len(code) == 8

#     # 4) Get summary report
#     res = client.get("/admin/reports/summary", headers=headers)
#     assert res.status_code == 200
