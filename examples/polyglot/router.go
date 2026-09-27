package fixture
// This file is deliberately review-only: no native Go parser is claimed.
func selectPath(state string) string {
    if state == "ready" { return "inspect" }
    return "stop"
}
