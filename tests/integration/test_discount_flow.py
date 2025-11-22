# def test_discount_n_update(client):
#     res = client.post("/auth/admin/login", json={
#         "username": "admin",
#         "password": "admin",
#     })
#     assert res.status_code == 200

#     token = res.json()["access_token"]
#     headers = {"Authorization": f"Bearer {token}"}

#     res = client.put("/admin/config/discount-n", json={
#         "n": 3,
#         "discount_percentage": 15
#     }, headers=headers)

#     assert res.status_code == 200
#     assert "15% discount applies every 3rd order" in res.json()["message"]
