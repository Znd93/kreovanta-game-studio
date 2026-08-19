from agents.producer import run_producer
from agents.researcher import run_researcher
from agents.game_director import run_game_director


founder_request = "Find a simple Roblox game opportunity."


producer_result = run_producer(founder_request)

print("\n=== PRODUCER ===")
print(producer_result["producer_message"])


research_response = run_researcher(
    producer_result["research_task"]
)

print("\n=== RESEARCHER ===")
print(research_response)


director_response = run_game_director(
    research_response
)

print("\n=== GAME DIRECTOR ===")
print(director_response)


print("\n=== STATUS ===")
print("WAITING FOR FOUNDER APPROVAL")

founder_decision = input(
    "\nFounder decision [APPROVE / CHANGE / REJECT]: "
).strip().upper()

if founder_decision == "APPROVE":
    print("\n=== FOUNDER DECISION ===")
    print("APPROVED")
    print("Game plan may continue to the next development stage.")

elif founder_decision == "CHANGE":
    print("\n=== FOUNDER DECISION ===")
    print("CHANGES REQUESTED")
    print("The plan must return to Game Director before development.")

elif founder_decision == "REJECT":
    print("\n=== FOUNDER DECISION ===")
    print("REJECTED")
    print("Development is blocked.")

else:
    print("\n=== FOUNDER DECISION ===")
    print("INVALID DECISION")
    print("Development remains blocked.")