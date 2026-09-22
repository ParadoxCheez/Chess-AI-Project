#Imports
import time
import random

#Chessmaker Imports
from extension.board_utils import list_legal_moves_for

#Scores for evaluation
CHECKMATE_SCORE = 100000
STALEMATE_SCORE = 0
DELTA_MARGIN = 9  # Queen value for aggressive pruning
MAX_QUIESCE_DEPTH = 12  # Limit quiescence depth


pieceValues = {
    "King": 0, 
    "Queen": 9.0, 
    "Right": 8.0, 
    "Bishop": 3.0, 
    "Knight": 3.0, 
    "Pawn": 1.0
}

#Evaluation tables for positional bonuses

#Encourage pushing pawns. Rank 1 (index 5-9) is one square from promotion.
pawnTable = [
    0,    0,    0,    0,    0,    # Rank 0: Promotion (Handled by material change P->Q)
    0.90, 0.90, 0.90, 0.90, 0.90, # Rank 1: Near promotion
    0.40, 0.40, 0.45, 0.40, 0.40, # Rank 2: Advanced
    0.15, 0.15, 0.20, 0.15, 0.15, # Rank 3: Developed
    0.05, 0.05, 0.10, 0.05, 0.05  # Rank 4: Start
]

#Bonus for Passed Pawns (No enemies ahead). 
passedPawnBonus = [
    0,    # Rank 0 (Promoted)
    1.5,  # Rank 1 (Almost there - worth 1.5 pawns)
    0.80, # Rank 2
    0.30, # Rank 3
    0     # Rank 4
]

knightTable = [
    -0.20, -0.10, -0.10, -0.10, -0.20,
    -0.10,  0.05,  0.10,  0.05, -0.10,
    -0.10,  0.10,  0.20,  0.10, -0.10,
    -0.10,  0.05,  0.10,  0.05, -0.10,
    -0.20, -0.10, -0.10, -0.10, -0.20
]

centerTable = [
    -0.10, -0.05, -0.05, -0.05, -0.10,
    -0.05,  0.05,  0.10,  0.05, -0.05,
    -0.05,  0.10,  0.15,  0.10, -0.05,
    -0.05,  0.05,  0.10,  0.05, -0.05,
    -0.10, -0.05, -0.05, -0.05, -0.10
]

kingEndgameTable = [
    -0.30, -0.20, -0.20, -0.20, -0.30,
    -0.20,  0,     0.05,  0,    -0.20,
    -0.20,  0.05,  0.10,  0.05, -0.20,
    -0.20,  0,     0.05,  0,    -0.20,
    -0.30, -0.20, -0.20, -0.20, -0.30
]

class TimeoutException(Exception):
    """
    To prevent timeout during minimax
    """
    pass

class TranspositionTable:
    """
    Used to store previously repeated positions to prevent repeated analysis of board positions
    """
    def __init__(self, max_size=500000):
        self.table = {}
        self.max_size = max_size
    
    def store(self, key, depth, score, flag, best_move):
        if len(self.table) >= self.max_size:
            # Simple eviction: remove random entries
            keys_to_remove = random.sample(list(self.table.keys()), self.max_size // 10)
            for k in keys_to_remove:
                del self.table[k]
        self.table[key] = (depth, score, flag, best_move)
    
    def probe(self, key):
        return self.table.get(key)
    
    def clear(self):
        self.table.clear()

#Constants used for transposition table entries 
EXACT, LOWER_BOUND, UPPER_BOUND = 0, 1, 2

#Global transposition table
tt = TranspositionTable()

#Moves that caused beta cutoffs at each ply, killer moves
killer_moves = [[None, None] for _ in range(100)]

#History heuristic
history_table = {}

class chessBoard:
    """
    To prevent calling the chessmaker board, I made chessboard class is made to speed up the computation
    """
    def __init__(self, board=None):
        self.board = [['.' for _ in range(5)] for _ in range(5)]
        self.white_turn = True
        self.ep_target = None  #Tracks En Passant target square (row, col)
        
        #Piece values for evaluation
        self.values = {
            'P': 1.0, 'N': 3.0, 'B': 3.0, 'R': 8.0, 'Q': 9.0, 'K': 0,
            'p': -1.0, 'n': -3.0, 'b': -3.0, 'r': -8.0, 'q': -9.0, 'k': 0,
            '.': 0
        }
        
        #King positions for quick check detection
        self.white_king_pos = None
        self.black_king_pos = None

        #Initialize board 
        if board:
            self.white_turn = (board.current_player.name == "white") 
            
            for p in board.get_pieces():
                c, r = p.position 
                
                #Create the board characters for White and Black
                char = p.name[0].upper() if p.player.name == "white" else p.name[0].lower()
                
                #Make the notation
                if p.name == "Knight": char = 'N' if p.player.name == "white" else 'n'
                if p.name == "Right": char = 'R' if p.player.name == "white" else 'r'
                if p.name == "King": 
                    char = 'K' if p.player.name == "white" else 'k'
                    if p.player.name == "white":
                        self.white_king_pos = (r, c)
                    else:
                        self.black_king_pos = (r, c)
                
                #Create the board
                if 0 <= r < 5 and 0 <= c < 5:
                    self.board[r][c] = char

    def get_zobrist_key(self):
        """
        Creates a hash for the current board position for transposition table lookup
        """
        return hash((tuple(tuple(row) for row in self.board), self.white_turn, self.ep_target))

    def make_move(self, move):
        """
        Executes a move and returns the state required to undo it.
        State: (captured_piece, old_ep_target, is_promotion, is_ep_capture)
        """
        sr, sc, er, ec = move
        piece = self.board[sr][sc]
        captured = self.board[er][ec]
        
        old_ep_target = self.ep_target
        self.ep_target = None #Reset EP target by default
        
        is_promotion = False
        is_ep_capture = False
        
        #Update king position tracking
        if piece == 'K':
            self.white_king_pos = (er, ec)
        elif piece == 'k':
            self.black_king_pos = (er, ec)
        
        #Pawn Logic
        if piece.upper() == 'P':
            #Promotion: White reaches row 0, Black reaches row 4
            if (piece.isupper() and er == 0) or (not piece.isupper() and er == 4):
                is_promotion = True
                piece = 'Q' if piece.isupper() else 'q'
            
            #Double Move for starting pawns
            #White (moves -1) from 3 to 1; Black (moves +1) from 1 to 3
            elif abs(sr - er) == 2:
                self.ep_target = ((sr + er) // 2, sc)
                
            #En Passant Capture
            elif (er, ec) == old_ep_target:
                is_ep_capture = True
                #Capture is on the starting row (sr), same column as end (ec)
                captured = self.board[sr][ec] 
                self.board[sr][ec] = '.'

        self.board[er][ec] = piece
        self.board[sr][sc] = '.'
        self.white_turn = not self.white_turn
        
        return (captured, old_ep_target, is_promotion, is_ep_capture)

    def undo_move(self, move, state):
        """
        Reverses the move using the stored state.
        """
        sr, sc, er, ec = move
        captured, old_ep_target, is_promotion, is_ep_capture = state
        
        piece = self.board[er][ec]
        
        #Revert Promotion
        if is_promotion:
            piece = 'P' if piece == 'Q' else 'p'
        
        #Update king position tracking
        if piece == 'K':
            self.white_king_pos = (sr, sc)
        elif piece == 'k':
            self.black_king_pos = (sr, sc)
        
        self.board[sr][sc] = piece
        self.ep_target = old_ep_target
        
        if is_ep_capture:
            self.board[er][ec] = '.'
            self.board[sr][ec] = captured # Put captured pawn back
        else:
            self.board[er][ec] = captured
            
        self.white_turn = not self.white_turn

    def is_passed_pawn(self, r, c, is_white):
        """
        Checks if a pawn at (r,c) is passed (no enemy pawns ahead in same or adjacent files).
        """
        direction = -1 if is_white else 1
        enemy_pawn = 'p' if is_white else 'P'
        
        #Check files c-1, c, c+1
        files_to_check = []
        if c > 0: files_to_check.append(c-1)
        files_to_check.append(c)
        if c < 4: files_to_check.append(c+1)
        
        #Check all rows ahead
        curr_r = r + direction
        while 0 <= curr_r < 5:
            for check_c in files_to_check:
                if self.board[curr_r][check_c] == enemy_pawn:
                    return False
            curr_r += direction
            
        return True

    def is_square_attacked(self, r, c, by_white):
        """
        Check if a square is attacked by the given color
        """
        attacker_char = str.isupper if by_white else str.islower
        
        #Check pawn attacks
        pawn_dir = -1 if by_white else 1
        #Pawns attack diagonally forward
        attack_row = r - pawn_dir 
        if 0 <= attack_row < 5:
            for dc in [-1, 1]:
                ac = c + dc
                if 0 <= ac < 5:
                    p = self.board[attack_row][ac]
                    if p in ('P' if by_white else 'p'):
                        return True
        
        #Check knight attacks (Knight, Right)
        knight_moves = [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]
        for dr, dc in knight_moves:
            ar, ac = r + dr, c + dc
            if 0 <= ar < 5 and 0 <= ac < 5:
                p = self.board[ar][ac]
                if attacker_char(p) and p.upper() in ['R', 'N']:
                    return True
        
        #Check diagonals (Bishop, Queen)
        for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            ar, ac = r + dr, c + dc
            while 0 <= ar < 5 and 0 <= ac < 5:
                p = self.board[ar][ac]
                if p != '.':
                    if attacker_char(p) and p.upper() in ['B', 'Q']:
                        return True
                    break
                ar, ac = ar + dr, ac + dc
        
        #Orthogonal (Right, Queen)
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            ar, ac = r + dr, c + dc
            while 0 <= ar < 5 and 0 <= ac < 5:
                p = self.board[ar][ac]
                if p != '.':
                    if attacker_char(p) and p.upper() in ['R', 'Q']:
                        return True
                    break
                ar, ac = ar + dr, ac + dc
        
        #Check king attacks
        for dr, dc in [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]:
            ar, ac = r + dr, c + dc
            if 0 <= ar < 5 and 0 <= ac < 5:
                p = self.board[ar][ac]
                if p in ('K' if by_white else 'k'):
                    return True
        
        return False

    def is_in_check(self, is_white):
        """
        Check if the king of given color is in check
        """
        king_pos = self.white_king_pos if is_white else self.black_king_pos
        if king_pos is None:
            return False
        kr, kc = king_pos
        return self.is_square_attacked(kr, kc, not is_white)

    def get_legal_moves(self):
        """
        Generates all legal moves (filters out moves leaving king in check)
        """
        pseudo_legal = self._get_pseudo_legal_moves()
        legal = []
        is_white = self.white_turn
        
        for move in pseudo_legal:
            state = self.make_move(move)
            if not self.is_in_check(is_white):
                legal.append(move)
            self.undo_move(move, state)
        
        return legal

    def _get_pseudo_legal_moves(self):
        """
        Generates all pseudo-legal moves.
        Includes Double Pawn Move and En Passant.
        """
        moves = []
        rows, cols = 5, 5
        
        ortho = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        diag = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
        knight_moves = [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]

        for r in range(rows):
            for c in range(cols):
                p = self.board[r][c]
                if p == '.': continue
                
                is_white = p.isupper()
                if is_white != self.white_turn: continue
                
                type_code = p.upper()
                directions = []
                is_single_step = False
                
                #Pawn move and capture rules
                if type_code == 'P': # Pawn
                    dr = -1 if is_white else 1 
                    
                    #Single Move forward
                    if 0 <= r+dr < rows and self.board[r+dr][c] == '.':
                        moves.append((r, c, r+dr, c))
                        
                        #Double Move from start rank
                        start_rank = 3 if is_white else 1
                        if r == start_rank:
                            if 0 <= r + 2*dr < rows and self.board[r + 2*dr][c] == '.':
                                moves.append((r, c, r + 2*dr, c))

                    #Capture (Normal + En Passant)
                    for dc in [-1, 1]:
                        if 0 <= r+dr < rows and 0 <= c+dc < cols:
                            target_sq = (r+dr, c+dc)
                            target_piece = self.board[r+dr][c+dc]
                            
                            #Normal Capture
                            if target_piece != '.' and target_piece.isupper() != is_white:
                                moves.append((r, c, r+dr, c+dc))
                            
                            #En Passant Capture
                            elif target_sq == self.ep_target:
                                moves.append((r, c, r+dr, c+dc))
                    continue 
                
                #Attributing piece legal moves
                elif type_code == 'N': directions = knight_moves; is_single_step = True
                elif type_code == 'B': directions = diag
                elif type_code == 'R': directions = ortho + knight_moves
                elif type_code == 'Q': directions = ortho + diag
                elif type_code == 'K': directions = ortho + diag; is_single_step = True
                
                for dr, dc in directions:
                    nr, nc = r, c
                    while True:
                        if is_single_step: #King/Knight
                            nr, nc = r + dr, c + dc
                        else: #Sliding pieces
                            nr, nc = nr + dr, nc + dc

                        if not (0 <= nr < rows and 0 <= nc < cols): break
                        
                        target = self.board[nr][nc]
                        
                        if target == '.':
                            moves.append((r, c, nr, nc))
                        elif target.isupper() != is_white:
                            moves.append((r, c, nr, nc)) #Capture
                            break
                        else:
                            break #Blocked by piece of same colour
                        
                        if is_single_step: break
        return moves

    def evaluate(self):
        """
        Evaluate the board position using material and positional values
        Returns a score from White's perspective
        """
        score = 0
        total_material = 0

        for r in range(5):
            for c in range(5):
                piece = self.board[r][c]
                if piece == '.':
                    continue
                
                piece_type = piece.upper()
                is_white = piece.isupper()
                multiplier = 1 if is_white else -1
                
                #Material value
                base_value = self.values.get(piece, 0)
                score += base_value
                total_material += abs(base_value)
                
                #Positional bonuses
                if is_white:
                    idx = r * 5 + c
                else:
                    idx = (4 - r) * 5 + c #Mirror for black
                
                if piece_type == 'P':
                    score += multiplier * pawnTable[idx]
                    #Passed Pawn Logic
                    if self.is_passed_pawn(r, c, is_white):
                        rank_idx = r if is_white else (4-r)
                        score += multiplier * passedPawnBonus[rank_idx]
                        
                elif piece_type == 'N':
                    score += multiplier * knightTable[idx]
                elif piece_type in ['B', 'Q', 'R']:
                    score += multiplier * centerTable[idx]
                elif piece_type == 'K':
                    #King safety in middlegame, activity in endgame
                    if total_material > 20:  # Middlegame (more than ~2 queens worth)
                        score += multiplier * (-centerTable[idx] / 2)
                    else:  #Endgame
                        score += multiplier * kingEndgameTable[idx]
        
        #Tempo bonus - slight advantage for side to move
        if self.white_turn:
            score += 0.1
        else:
            score -= 0.1
        
        return score

    def is_checkmate(self):
        """
        Check if current position is checkmate
        """
        is_white = self.white_turn
        if not self.is_in_check(is_white):
            return False
        return len(self.get_legal_moves()) == 0

    def is_stalemate(self):
        """
        Check if current position is stalemate
        """
        is_white = self.white_turn
        if self.is_in_check(is_white):
            return False
        return len(self.get_legal_moves()) == 0


#Choice of order of moves
def order_moves(shadow, moves, ply, tt_move=None):
    """
    Advanced move ordering
    """
    scored_moves = []
    
    for move in moves:
        sr, sc, er, ec = move
        score = 0
        
        #Hash-move from transposition table gets highest priority
        if tt_move and move == tt_move:
            score = 1000000
        else:
            piece = shadow.board[sr][sc]
            captured = shadow.board[er][ec]
            
            #Check En Passant capture for ordering
            if piece.upper() == 'P' and captured == '.' and sc != ec:
                captured = 'P' if piece.islower() else 'p'
            
            #MVV-LVA for captures
            if captured != '.':
                victim_value = abs(shadow.values.get(captured, 0))
                attacker_value = abs(shadow.values.get(piece, 0))
                score = 10000 + victim_value * 10 - attacker_value
            
            #Promotion bonus
            if piece.upper() == 'P' and (er == 0 or er == 4):
                 score += 5000

            #Killer moves
            elif ply < 100:
                if killer_moves[ply][0] == move:
                    score = 9000
                elif killer_moves[ply][1] == move:
                    score = 8000
                else:
                    #History heuristic
                    score = history_table.get(move, 0)
        
        scored_moves.append((score, move))
    
    scored_moves.sort(reverse=True, key=lambda x: x[0])
    return [move for _, move in scored_moves]


#Main agent function
def agent(board, player, var):
    """
    Main agent function using Minimax with Alpha-Beta pruning, Iterative Deepening with created chessboard
    """
    ply_id, time_budget = var[0], var[1]
    start_time = time.perf_counter()
    time_limit = start_time + time_budget - 5  # Safety margin

    #Convert chessmaker board to created chessboard
    shadow = chessBoard(board)
    is_maximizing = (player.name == "white") 

    best_move_coords = None
    current_depth = 1
    max_depth = 50

    print(f"\n--- Ply {ply_id}: Thinking ({time_budget}s limit) ---")
    
    #Clear killer moves and history for new position
    for i in range(100):
        killer_moves[i] = [None, None]
    history_table.clear()

    try:
        while current_depth <= max_depth:
            if time.perf_counter() > time_limit: 
                break

            #Search on created chessboard with aspiration windows for more beta cutoffs
            if current_depth >= 4 and best_move_coords:
                #Try narrow window first
                window = 0.50
                alpha = -window
                beta = window
                score, move_coords = minimax_shadow_root(shadow, current_depth, is_maximizing, 
                                                         alpha, beta, time_limit, 0)
                
                #If outside window, re-search with full window
                if score <= alpha or score >= beta:
                    score, move_coords = minimax_shadow_root(shadow, current_depth, is_maximizing,
                                                            -float('inf'), float('inf'), time_limit, 0)
            else:
                score, move_coords = minimax_shadow_root(shadow, current_depth, is_maximizing,
                                                        -float('inf'), float('inf'), time_limit, 0)
            
            if move_coords:
                best_move_coords = move_coords
                
            print(f">>> Depth {current_depth} completed. Score: {score}")
            
            #Checkmate found
            if abs(score) > CHECKMATE_SCORE - 100: 
                break
            
            current_depth += 1

    except TimeoutException:
        print(f"!!! Time limit reached. Returning best move from depth {current_depth - 1}.")
        
    #Convert best move coordinates back to chessmaker piece and move objects
    if best_move_coords:
        sr, sc, er, ec = best_move_coords
        
        legal = list_legal_moves_for(board, player)
        for piece, move in legal:
            #Match the starting piece position and the move end position
            if piece.position == (sc, sr) and move.position == (ec, er): 
                return piece, move

    #Fallback: if no move found
    legal = list_legal_moves_for(board, player)
    return random.choice(legal) if legal else (None, None)


def minimax_shadow_root(shadow_board, depth, maximizing, alpha, beta, time_limit, ply):
    """
    Root function for Minimax using the Shadow Board with transposition table
    """
    shadow = shadow_board
    is_maximizing = maximizing
    
    #Probe transposition table
    zobrist = shadow.get_zobrist_key()
    tt_entry = tt.probe(zobrist)
    tt_move = None
    
    if tt_entry:
        tt_depth, tt_score, tt_flag, tt_move = tt_entry
        if tt_depth >= depth:
            if tt_flag == EXACT:
                return tt_score, tt_move
            elif tt_flag == LOWER_BOUND:
                alpha = max(alpha, tt_score)
            elif tt_flag == UPPER_BOUND:
                beta = min(beta, tt_score)
            if alpha >= beta:
                return tt_score, tt_move
    
    legal_moves = shadow.get_legal_moves()
    
    #Check for terminal positions
    if not legal_moves:
        if shadow.is_in_check(is_maximizing):
            return -CHECKMATE_SCORE + ply, None  # Checkmate
        return STALEMATE_SCORE, None  # Stalemate
    
    #Order moves for better pruning
    legal_moves = order_moves(shadow, legal_moves, ply, tt_move)
    
    best_move = None
    original_alpha = alpha
    
    if is_maximizing:
        max_eval = -float('inf')
        for move in legal_moves:
            if time.perf_counter() > time_limit: 
                raise TimeoutException()
            
            state = shadow.make_move(move)
            eval_val, _ = minimax_shadow(shadow, depth - 1, False, alpha, beta, time_limit, ply + 1)
            shadow.undo_move(move, state)
            
            if eval_val > max_eval:
                max_eval = eval_val
                best_move = move
            
            alpha = max(alpha, eval_val)
            if beta <= alpha:
                #Update killer moves and the history
                captured = state[0]
                if captured == '.' and ply < 100:
                    if killer_moves[ply][0] != move:
                        killer_moves[ply][1] = killer_moves[ply][0]
                        killer_moves[ply][0] = move
                    history_table[move] = history_table.get(move, 0) + depth * depth
                break
        
        #Store position in the transposition table
        if max_eval <= original_alpha:
            flag = UPPER_BOUND
        elif max_eval >= beta:
            flag = LOWER_BOUND
        else:
            flag = EXACT
        tt.store(zobrist, depth, max_eval, flag, best_move)
        
        return max_eval, best_move
    else:
        min_eval = float('inf')
        for move in legal_moves:
            if time.perf_counter() > time_limit: 
                raise TimeoutException()

            state = shadow.make_move(move)
            eval_val, _ = minimax_shadow(shadow, depth - 1, True, alpha, beta, time_limit, ply + 1)
            shadow.undo_move(move, state)

            if eval_val < min_eval:
                min_eval = eval_val
                best_move = move
            
            beta = min(beta, eval_val)
            if beta <= alpha:
                captured = state[0]
                if captured == '.' and ply < 100:
                    if killer_moves[ply][0] != move:
                        killer_moves[ply][1] = killer_moves[ply][0]
                        killer_moves[ply][0] = move
                    history_table[move] = history_table.get(move, 0) + depth * depth
                break
        
        #Store in transposition table
        if min_eval >= beta:
            flag = LOWER_BOUND
        elif min_eval <= original_alpha:
            flag = UPPER_BOUND
        else:
            flag = EXACT
        tt.store(zobrist, depth, min_eval, flag, best_move)
        
        return min_eval, best_move


def minimax_shadow(shadow, depth, maximizing, alpha, beta, time_limit, ply):
    """
    Recursive function for Minimax using the Shadow (chessBoard) with Alpha-Beta pruning
    """
    if time.perf_counter() > time_limit: 
        raise TimeoutException()
    
    #Probe transposition table
    zobrist = shadow.get_zobrist_key()
    tt_entry = tt.probe(zobrist)
    tt_move = None
    
    if tt_entry:
        tt_depth, tt_score, tt_flag, tt_move = tt_entry
        if tt_depth >= depth:
            if tt_flag == EXACT:
                return tt_score, None
            elif tt_flag == LOWER_BOUND:
                alpha = max(alpha, tt_score)
            elif tt_flag == UPPER_BOUND:
                beta = min(beta, tt_score)
            if alpha >= beta:
                return tt_score, None
    
    #Base Case: Enter Quiescence Search at depth 0
    if depth == 0:
        return quiescence_shadow(shadow, maximizing, alpha, beta, time_limit, ply, 0), None

    legal_moves = shadow.get_legal_moves()
    
    if not legal_moves:
        #No legal moves means terminal node
        is_white = shadow.white_turn
        if shadow.is_in_check(is_white):
            #Checkmate, gets faster checkmates
            return (-CHECKMATE_SCORE + ply) if maximizing else (CHECKMATE_SCORE - ply), None
        return STALEMATE_SCORE, None  #Stalemate

    #Order moves
    legal_moves = order_moves(shadow, legal_moves, ply, tt_move)
    
    best_move = None
    original_alpha = alpha

    if maximizing:
        max_eval = -float('inf')
        for move in legal_moves:
            state = shadow.make_move(move)
            eval_val, _ = minimax_shadow(shadow, depth - 1, False, alpha, beta, time_limit, ply + 1)
            shadow.undo_move(move, state)
            
            if eval_val > max_eval:
                max_eval = eval_val
                best_move = move
            
            alpha = max(alpha, eval_val)
            if beta <= alpha:
                captured = state[0]
                if captured == '.' and ply < 100:
                    if killer_moves[ply][0] != move:
                        killer_moves[ply][1] = killer_moves[ply][0]
                        killer_moves[ply][0] = move
                    history_table[move] = history_table.get(move, 0) + depth * depth
                break
        
        #Store in TT
        if max_eval <= original_alpha:
            flag = UPPER_BOUND
        elif max_eval >= beta:
            flag = LOWER_BOUND
        else:
            flag = EXACT
        tt.store(zobrist, depth, max_eval, flag, best_move)
        
        return max_eval, None
    else:
        min_eval = float('inf')
        for move in legal_moves:
            state = shadow.make_move(move)
            eval_val, _ = minimax_shadow(shadow, depth - 1, True, alpha, beta, time_limit, ply + 1)
            shadow.undo_move(move, state)
            
            if eval_val < min_eval:
                min_eval = eval_val
                best_move = move
            
            beta = min(beta, eval_val)
            if beta <= alpha:
                captured = state[0]
                if captured == '.' and ply < 100:
                    if killer_moves[ply][0] != move:
                        killer_moves[ply][1] = killer_moves[ply][0]
                        killer_moves[ply][0] = move
                    history_table[move] = history_table.get(move, 0) + depth * depth
                break
        
        #Store in TT
        if min_eval >= beta:
            flag = LOWER_BOUND
        elif min_eval <= original_alpha:
            flag = UPPER_BOUND
        else:
            flag = EXACT
        tt.store(zobrist, depth, min_eval, flag, best_move)
        
        return min_eval, None


def quiescence_shadow(shadow, maximizing, alpha, beta, time_limit, ply, quiesce_depth):
    """
    Quiescence Search using the Shadow Board
    """
    if time.perf_counter() > time_limit: 
        raise TimeoutException()
    
    #Limit quiescence depth
    if quiesce_depth >= MAX_QUIESCE_DEPTH:
        return shadow.evaluate()

    stand_pat = shadow.evaluate()

    #Alpha-Beta and Delta Pruning
    if maximizing:
        if stand_pat >= beta: 
            return beta
        if stand_pat > alpha: 
            alpha = stand_pat
        #Delta pruning
        if stand_pat < alpha - DELTA_MARGIN:
            return alpha
    else:
        if stand_pat <= alpha: 
            return alpha
        if stand_pat < beta: 
            beta = stand_pat
        #Delta pruning
        if stand_pat > beta + DELTA_MARGIN:
            return beta

    #Generate captures only
    capture_moves = []
    
    for r, c, er, ec in shadow._get_pseudo_legal_moves():
        captured_char = shadow.board[er][ec]
        move = (r, c, er, ec)
        
        #Identify En Passant captures 
        piece = shadow.board[r][c]
        is_ep = False
        if piece.upper() == 'P' and captured_char == '.' and c != ec:
            is_ep = True
            captured_char = 'P' if piece.islower() else 'p' #Phantom capture for valuation (similar to board copy)

        if captured_char != '.' or is_ep:
            #Check if move is legal
            is_white = shadow.white_turn
            state = shadow.make_move(move)
            if not shadow.is_in_check(is_white):
                #Calculate MVV-LVA score
                victim_val = abs(shadow.values.get(captured_char, 0))
                attacker_char = shadow.board[er][ec]
                attacker_val = abs(shadow.values.get(attacker_char, 0))
                
                priority = 10 * victim_val - attacker_val
                capture_moves.append((priority, move))
            shadow.undo_move(move, state)

    #Sort: Highest priority first (MVV-LVA ordering)
    capture_moves.sort(key=lambda x: x[0], reverse=True)

    if maximizing:
        for _, move in capture_moves:
            state = shadow.make_move(move)
            score = quiescence_shadow(shadow, False, alpha, beta, time_limit, ply + 1, quiesce_depth + 1)
            shadow.undo_move(move, state)
            
            if score >= beta: 
                return beta
            if score > alpha: 
                alpha = score
        return alpha
    else:
        for _, move in capture_moves:
            state = shadow.make_move(move)
            score = quiescence_shadow(shadow, True, alpha, beta, time_limit, ply + 1, quiesce_depth + 1)
            shadow.undo_move(move, state)
            
            if score <= alpha: 
                return alpha
            if score < beta: 
                beta = score
        return beta

def get_opponent(board, player):
    for p in board.players:
        if p.name != player.name:
            return p
    return board.players[0]