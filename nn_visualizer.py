"""
Neural Network Visualizer — Python backend

Run:
    python3 nn_visualizer.py

Then open http://localhost:8080 in your browser.

Uses only the Python standard library.
"""

import copy
import json
import math
import random
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler


# ── Activation helpers ──────────────────────────────────────────
def _sigmoid(z):
    z = max(-500.0, min(500.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def _sigmoid_deriv(z):
    s = _sigmoid(z)
    return s * (1.0 - s)


def _relu(z):
    return max(0.0, z)


def _relu_deriv(z):
    return 1.0 if z > 0 else 0.0


# ── Network class ───────────────────────────────────────────────
class Network:
    """Stateful neural network with forward pass, backpropagation, and
    snapshot history for stepping backwards."""

    def __init__(self, layer_sizes, activation="relu", softmax=False,
                 input_values=None, targets=None):
        self.layer_sizes = list(layer_sizes)
        self.activation = activation
        self.softmax = softmax
        self.epoch = 0

        self.act_fn = _sigmoid if activation == "sigmoid" else _relu
        self.act_deriv = _sigmoid_deriv if activation == "sigmoid" else _relu_deriv

        # Xavier-init weights from deterministic seed
        random.seed(hash(tuple(self.layer_sizes)))

        self.weights = []  # weights[l][i][j]: layer l, from-node i, to-node j
        self.biases = []   # biases[l][j]:  layer l, node j

        for l in range(1, len(self.layer_sizes)):
            fan_in = self.layer_sizes[l - 1]
            fan_out = self.layer_sizes[l]
            limit = math.sqrt(6.0 / (fan_in + fan_out))
            W = [[random.uniform(-limit, limit) for _ in range(fan_out)]
                 for _ in range(fan_in)]
            b = [random.uniform(-0.1, 0.1) for _ in range(fan_out)]
            self.weights.append(W)
            self.biases.append(b)

        # Input values
        if input_values and len(input_values) == self.layer_sizes[0]:
            self.inputs = list(input_values)
        else:
            self.inputs = list(range(1, self.layer_sizes[0] + 1))

        # Target values
        out_size = self.layer_sizes[-1]
        if targets and len(targets) == out_size:
            self.targets = list(targets)
        else:
            self.targets = [1.0] * out_size

        # Run initial forward pass
        self.z_vals = []      # pre-activation values
        self.a_vals = []      # post-activation values (activations)
        self.loss = 0.0
        self.gradients = None
        self.forward()

        # Snapshot history for stepping back
        self._history = []

    def forward(self):
        """Compute forward pass, storing z and a for each layer."""
        self.z_vals = [None]  # input layer has no z
        self.a_vals = [list(self.inputs)]

        num_weight_layers = len(self.weights)
        for l in range(num_weight_layers):
            prev = self.a_vals[-1]
            fan_in = len(prev)
            fan_out = self.layer_sizes[l + 1]
            is_output = (l == num_weight_layers - 1)
            z_layer = []
            a_layer = []
            for j in range(fan_out):
                z = sum(prev[i] * self.weights[l][i][j]
                        for i in range(fan_in)) + self.biases[l][j]
                z_layer.append(z)
                # Output layer uses linear activation; hidden layers use chosen activation
                if is_output:
                    a_layer.append(z)
                else:
                    a_layer.append(self.act_fn(z))
            self.z_vals.append(z_layer)
            self.a_vals.append(a_layer)

        # Optional softmax on output layer
        if self.softmax and len(self.a_vals[-1]) > 1:
            raw = self.a_vals[-1]
            max_val = max(raw)
            exps = [math.exp(v - max_val) for v in raw]
            total = sum(exps)
            self.a_vals[-1] = [e / total for e in exps]

        # MSE loss
        out = self.a_vals[-1]
        n = len(out)
        self.loss = sum((out[i] - self.targets[i]) ** 2 for i in range(n)) / n

        self.compute_gradients()

    def compute_gradients(self):
        """Compute dL/dw for all weights at current network state."""
        num_weight_layers = len(self.weights)
        out = self.a_vals[-1]
        n = len(out)

        if self.softmax and n > 1:
            dl_ds = [(2.0 / n) * (out[i] - self.targets[i]) for i in range(n)]
            sm = out
            delta = [0.0] * n
            for j in range(n):
                for ii in range(n):
                    kronecker = 1.0 if ii == j else 0.0
                    delta[j] += dl_ds[ii] * sm[ii] * (kronecker - sm[j])
        else:
            delta = [(2.0 / n) * (out[j] - self.targets[j]) for j in range(n)]

        deltas = [None] * num_weight_layers
        deltas[-1] = delta

        for l in range(num_weight_layers - 2, -1, -1):
            fan_out_prev = len(deltas[l + 1])
            fan_out_curr = self.layer_sizes[l + 1]
            z_layer = self.z_vals[l + 1]
            new_delta = []
            for k in range(fan_out_curr):
                s_val = sum(self.weights[l + 1][k][j] * deltas[l + 1][j]
                            for j in range(fan_out_prev))
                new_delta.append(s_val * self.act_deriv(z_layer[k]))
            deltas[l] = new_delta

        self.gradients = []
        for l in range(num_weight_layers):
            a_prev = self.a_vals[l]
            fan_in = len(a_prev)
            fan_out = len(deltas[l])
            grad_layer = []
            for i in range(fan_in):
                grad_row = []
                for j in range(fan_out):
                    grad_row.append(a_prev[i] * deltas[l][j])
                grad_layer.append(grad_row)
            self.gradients.append(grad_layer)

    def backward(self, lr):
        """Backpropagate and update weights/biases."""
        num_weight_layers = len(self.weights)
        out = self.a_vals[-1]
        n = len(out)

        # Compute output layer delta (output layer uses linear activation, deriv = 1)
        if self.softmax and n > 1:
            # dL/ds = (2/n)(s - t)
            dl_ds = [(2.0 / n) * (out[i] - self.targets[i]) for i in range(n)]
            # Softmax Jacobian: dL/da[j] = sum_i(dL/ds[i] * s[i] * (delta_ij - s[j]))
            s = out  # softmax output
            delta = [0.0] * n
            for j in range(n):
                for i in range(n):
                    kronecker = 1.0 if i == j else 0.0
                    delta[j] += dl_ds[i] * s[i] * (kronecker - s[j])
        else:
            # Output is linear: dL/dz = (2/n)(a - t)
            delta = [(2.0 / n) * (out[j] - self.targets[j]) for j in range(n)]

        # Store deltas per layer (index 0 = first weight layer)
        deltas = [None] * num_weight_layers
        deltas[-1] = delta

        # Backpropagate deltas to hidden layers
        for l in range(num_weight_layers - 2, -1, -1):
            fan_out_prev = len(deltas[l + 1])
            fan_out_curr = self.layer_sizes[l + 1]
            z_layer = self.z_vals[l + 1]
            new_delta = []
            for k in range(fan_out_curr):
                s = sum(self.weights[l + 1][k][j] * deltas[l + 1][j]
                        for j in range(fan_out_prev))
                new_delta.append(s * self.act_deriv(z_layer[k]))
            deltas[l] = new_delta

        # Update weights and biases
        for l in range(num_weight_layers):
            a_prev = self.a_vals[l]
            fan_in = len(a_prev)
            fan_out = len(deltas[l])
            for i in range(fan_in):
                for j in range(fan_out):
                    self.weights[l][i][j] -= lr * a_prev[i] * deltas[l][j]
            for j in range(fan_out):
                self.biases[l][j] -= lr * deltas[l][j]

    def _snapshot(self):
        """Return a deep copy of weights and biases."""
        return (copy.deepcopy(self.weights), copy.deepcopy(self.biases))

    def train_step(self, lr, inputs=None, targets=None):
        """One training step: forward → backward → update."""
        if inputs is not None and len(inputs) == self.layer_sizes[0]:
            self.inputs = list(inputs)
        if targets is not None and len(targets) == self.layer_sizes[-1]:
            self.targets = list(targets)

        # Save snapshot before update
        self._history.append(self._snapshot())
        if len(self._history) > 10000:
            self._history.pop(0)

        self.forward()
        self.backward(lr)
        self.epoch += 1
        self.forward()  # post-update state

    def step_back(self):
        """Revert to previous snapshot."""
        if not self._history:
            return False
        self.weights, self.biases = self._history.pop()
        self.epoch = max(0, self.epoch - 1)
        self.forward()
        return True

    def to_dict(self):
        """Serialize network state to JSON-compatible dict."""
        # Build labels and node names
        num_layers = len(self.layer_sizes)
        labels = []
        node_names = []
        for i in range(num_layers):
            if i == 0:
                labels.append("Input")
            elif i == num_layers - 1:
                labels.append("Output")
            else:
                labels.append(f"Hidden {i}")

            layer_names = []
            for j in range(self.layer_sizes[i]):
                if i == 0:
                    layer_names.append(f"x{j + 1}")
                elif i == num_layers - 1:
                    layer_names.append(f"y{j + 1}")
                else:
                    layer_names.append(f"h{i}.{j + 1}")
            node_names.append(layer_names)

        total_params = sum(
            self.layer_sizes[i - 1] * self.layer_sizes[i] + self.layer_sizes[i]
            for i in range(1, num_layers)
        )

        # Round values for JSON
        node_values = []
        for layer in self.a_vals:
            node_values.append([round(v, 4) for v in layer])

        weights_rounded = []
        for W in self.weights:
            weights_rounded.append([[round(w, 4) for w in row] for row in W])

        biases_rounded = []
        for b in self.biases:
            biases_rounded.append([round(v, 4) for v in b])

        gradients_rounded = []
        if self.gradients:
            for G in self.gradients:
                gradients_rounded.append([[round(g, 6) for g in row] for row in G])

        return {
            "layers": self.layer_sizes,
            "labels": labels,
            "node_names": node_names,
            "node_values": node_values,
            "weights": weights_rounded,
            "biases": biases_rounded,
            "gradients": gradients_rounded,
            "activation": self.activation,
            "softmax": self.softmax,
            "total_params": total_params,
            "num_layers": num_layers,
            "feature_count": self.layer_sizes[0],
            "epoch": self.epoch,
            "loss": round(self.loss, 6),
            "targets": self.targets,
        }


# ── Compute layer sizes from parameters ─────────────────────────
def _compute_layer_sizes(num_layers, feature_count):
    """Return list of layer sizes using cosine-interpolated taper."""
    output_size = max(1, feature_count // 4)
    layers = []
    for i in range(num_layers):
        if num_layers == 1:
            size = feature_count
        elif i == 0:
            size = feature_count
        elif i == num_layers - 1:
            size = output_size
        else:
            t = i / (num_layers - 1)
            size = round(
                output_size + (feature_count - output_size)
                * (1 + math.cos(math.pi * t)) / 2
            )
            size = max(1, size)
        layers.append(size)
    return layers


# ── Global network instance ─────────────────────────────────────
_network = None


class NNHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/network":
            self._handle_network_api(parsed.query)
        elif parsed.path == "/":
            self.path = "/nn_visualizer.html"
            super().do_GET()
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/step":
            self._handle_step()
        elif parsed.path == "/api/back":
            self._handle_back()
        else:
            self.send_error(404)

    # ── Helpers ──────────────────────────────────────────────────
    def _send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw)

    # ── API handlers ─────────────────────────────────────────────
    def _handle_network_api(self, query_string):
        global _network

        params = urllib.parse.parse_qs(query_string)

        num_layers = int(params.get("layers", [4])[0])
        feature_count = int(params.get("features", [8])[0])
        activation = params.get("activation", ["relu"])[0]

        num_layers = max(2, min(num_layers, 5))
        feature_count = max(1, min(feature_count, 12))
        if activation not in ("relu", "sigmoid"):
            activation = "relu"
        softmax = params.get("softmax", ["0"])[0] == "1"

        # Parse custom input values
        inputs_raw = params.get("inputs", [None])[0]
        input_values = None
        if inputs_raw:
            try:
                input_values = [float(v) for v in inputs_raw.split(",")]
            except (ValueError, TypeError):
                input_values = None

        # Parse custom target values
        targets_raw = params.get("targets", [None])[0]
        targets = None
        if targets_raw:
            try:
                targets = [float(v) for v in targets_raw.split(",")]
            except (ValueError, TypeError):
                targets = None

        layer_sizes = _compute_layer_sizes(num_layers, feature_count)
        _network = Network(layer_sizes, activation, softmax, input_values, targets)
        self._send_json(_network.to_dict())

    def _handle_step(self):
        global _network
        if _network is None:
            self.send_error(400, "No network initialised")
            return

        body = self._read_json_body()
        lr = float(body.get("lr", 0.01))
        inputs = body.get("inputs")
        targets = body.get("targets")

        _network.train_step(lr, inputs, targets)
        self._send_json(_network.to_dict())

    def _handle_back(self):
        global _network
        if _network is None:
            self.send_error(400, "No network initialised")
            return

        _network.step_back()
        self._send_json(_network.to_dict())

    # suppress default request logging
    def log_message(self, format, *args):
        pass


def main():
    host, port = "localhost", 8080
    server = HTTPServer((host, port), NNHandler)
    print(f"Neural Network Visualizer running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
