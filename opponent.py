import random
from extension.board_utils import list_legal_moves_for

def opponent(board, player, var):
    """"
    This is an example of an random-move Opponent

    Parameters
    ----------
    board: the current chess board
    player: your assigned player role (white or black)
    var:  [ply, THINKING_TIME_BUDGET] a list cotaining the ply ID and the thinking_time_budget (secs)

    Returns
    -------
    piece: your selected chess piece
    move_opt: your selected move of your selected chess piece
    
    Hints:
    -----
    - List of players on the current board game: list(board.players) - default list: [Player (white), Player (black)]
    - board.players[0].name = "white" and board.players[1].name = "black"
    - Name of the player assigned to the Opponent (either "white" or "black"): player.name
    - list of pieces of the current player: list(board.get_player_pieces(player))
    - List of pieces and corresponding moves for each pieces of the player: piece, move_opt = list_legal_moves_for(board, player)
    - From var: ply = var[0], timeout = var[1]
    - Use the timeout variable together with time.perf_counter()
    to ensure the it returns its best move before the time limit expires.
    """
    piece, move_opt = None, None
    print(f"Ply: {var[0]}")

    if player.name == "white":

        while not move_opt:
            piece = random.choice(list(board.get_player_pieces(player)))
            mov = piece.get_move_options()
            if mov:
                move_opt = random.choice(mov)
                break
    else:
       
        while not move_opt:
            piece = random.choice(list(board.get_player_pieces(player)))
            mov = piece.get_move_options()
            if mov:
                move_opt = random.choice(mov)
                break

    return piece, move_opt
