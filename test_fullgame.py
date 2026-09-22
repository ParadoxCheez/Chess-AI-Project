# Python 3.11+
import sys, time
from itertools import cycle
from chessmaker.chess.base import Board
from extension.board_utils import print_board_ascii, copy_piece_move
from extension.board_rules import get_result, thinking_with_timeout, THINKING_TIME_BUDGET, GAME_TIME_BUDGET
from samples import white, black, sample0, sample1
from agent import agent
from old_agent import agent as old_agent
from opponent import opponent


def make_custom_board(board_sample):
    # player1: white vs player2: black
    players = [white, black]
    board = Board(
    squares = board_sample,
    players=players,
        turn_iterator=cycle(players),
    )
    return board, players

def testgame_timeout(p_white, p_black, board_sample):

    board, players = make_custom_board(board_sample)
    turn_order = cycle(players)
    print(f"Time budget for each move {THINKING_TIME_BUDGET} seconds")
    print(f"Time budget for the game: {GAME_TIME_BUDGET} seconds")
    print("=== Initial position ===")
    print_board_ascii(board)
    t_start = time.perf_counter()
    t_game = t_start + GAME_TIME_BUDGET
    ply = 1
    while True:
        try:
            # Checking game timeout
            now = time.perf_counter()
            if now > t_game:
                print("=== Game ended: Draw - game timeout ===")
                break
            
            player = next(turn_order)
            temp_board = board.clone()
            if player.name == "white":
                p_piece, p_move_opt = thinking_with_timeout(func=p_white, thinking_time=THINKING_TIME_BUDGET, board=temp_board, player=player, var=[ply, THINKING_TIME_BUDGET])
                board, piece, move_opt = copy_piece_move(board, p_piece, p_move_opt)
            else:
                p_piece, p_move_opt = thinking_with_timeout(func=p_black, thinking_time=THINKING_TIME_BUDGET, board=temp_board, player=player, var=[ply, THINKING_TIME_BUDGET])
                board, piece, move_opt = copy_piece_move(board, p_piece, p_move_opt)

            # Checking game timeout
            now = time.perf_counter()
            if now > t_game:
                print("=== Game ended: Draw - game timeout ===")
                break
            
            if (not piece) or (not move_opt):
                res = get_result(board)
                if res:
                    print(f"=== Game ended: {res} ===")
                elif p_piece == 99:
                    print(f"=== Game ended: {player.name} thinking time out ===")
                else:
                    print(f"=== Game ended: {player.name} can not make a legal move ===")
                break

            else:
                try:
                    piece.move(move_opt)
                    ply = ply + 1
                    print(f"{piece} move to: ({move_opt.position.x},{move_opt.position.y})")
                    if getattr(move_opt, "captures", None):
                        caps = ", ".join(f"({c.x},{c.y})" for c in move_opt.captures)
                        if caps:
                            print(f"{piece} captures at: {caps}")
                except Exception:
                    print(f"=== Game ended: {player.name} can not make a legal move ===")
                    break

            print_board_ascii(board)
            res = get_result(board)
            if res:
                print(f"=== Game ended: {res} ===")
                break

        except KeyboardInterrupt:
            print(f"=== Game ended by keyboard interuption ===")
            sys.exit()

if __name__ == "__main__":
    testgame_timeout(p_white=agent, p_black=old_agent, board_sample=sample0)

#a10e7298ebd0a2daa81347dac8aec8f690e698050e2a96fd6392ed71282e121d - Chess code
#MDK-456 code