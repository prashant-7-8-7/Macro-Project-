"""SQLite persistence for the existing study workspace; no external database."""
import json
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from src.database.db import get_connection


def new_id():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class StudyRepository:
    def collections(self):
        with closing(get_connection()) as db:
            return [dict(r) for r in db.execute('''SELECT c.*, count(cd.document_id) document_count
                FROM collections c LEFT JOIN collection_documents cd ON cd.collection_id=c.id
                GROUP BY c.id ORDER BY c.name''')]

    def create_collection(self, name):
        ident = new_id()
        with closing(get_connection()) as db, db:
            db.execute('INSERT INTO collections(id,name) VALUES (?,?)', (ident, name))
        return {'id': ident, 'name': name}

    def collection_scope(self, ident):
        with closing(get_connection()) as db:
            if not db.execute('SELECT 1 FROM collections WHERE id=?', (ident,)).fetchone():
                raise KeyError('Subject not found')
            return [r[0] for r in db.execute('SELECT document_id FROM collection_documents WHERE collection_id=? ORDER BY document_id', (ident,))]

    def assign_collection(self, ident, ids):
        with closing(get_connection()) as db, db:
            if not db.execute('SELECT 1 FROM collections WHERE id=?', (ident,)).fetchone():
                raise KeyError('Subject not found')
            if any(not db.execute('SELECT 1 FROM documents WHERE id=?', (doc,)).fetchone() for doc in ids):
                raise KeyError('Document not found')
            db.execute('DELETE FROM collection_documents WHERE collection_id=?', (ident,))
            db.executemany('INSERT INTO collection_documents VALUES (?,?)', [(ident, doc) for doc in ids])

    def delete_collection(self, ident):
        with closing(get_connection()) as db, db:
            db.execute('DELETE FROM collections WHERE id=?', (ident,))

    def sessions(self, document_id):
        with closing(get_connection()) as db:
            return [dict(r) for r in db.execute('SELECT * FROM chat_sessions WHERE document_id=? ORDER BY updated_at DESC, rowid DESC', (document_id,))]

    def session(self, ident):
        with closing(get_connection()) as db:
            row = db.execute('SELECT * FROM chat_sessions WHERE id=?', (ident,)).fetchone()
            return dict(row) if row else None

    def create_session(self, document_id, scope, title='New conversation'):
        ident = new_id()
        with closing(get_connection()) as db, db:
            db.execute('INSERT INTO chat_sessions(id,document_id,scope_json,title) VALUES (?,?,?,?)',
                       (ident, document_id, json.dumps(sorted(scope)), title[:120]))
        return self.session(ident)

    def messages(self, ident):
        with closing(get_connection()) as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM chat_messages WHERE session_id=? ORDER BY rowid', (ident,))]
        for row in rows:
            row['citations'] = json.loads(row.pop('citations_json'))
        return rows

    def add_message(self, ident, role, content, citations=None):
        with closing(get_connection()) as db, db:
            db.execute('INSERT INTO chat_messages(id,session_id,role,content,citations_json) VALUES (?,?,?,?,?)',
                       (new_id(), ident, role, content, json.dumps(citations or [])))
            db.execute('UPDATE chat_sessions SET updated_at=? WHERE id=?', (now(), ident))
            if role == 'user':
                db.execute("UPDATE chat_sessions SET title=? WHERE id=? AND title='New conversation'", (content[:80], ident))

    def delete_session(self, ident):
        with closing(get_connection()) as db, db:
            db.execute('DELETE FROM chat_sessions WHERE id=?', (ident,))

    def save_quiz(self, document_id, questions):
        ident = new_id()
        with closing(get_connection()) as db, db:
            db.execute('INSERT INTO study_quizzes(id,document_id,questions_json) VALUES (?,?,?)',
                       (ident, document_id, json.dumps(questions)))
        return ident

    def quiz(self, ident):
        with closing(get_connection()) as db:
            row = db.execute('SELECT * FROM study_quizzes WHERE id=?', (ident,)).fetchone()
        if not row:
            raise KeyError('Quiz not found')
        result = dict(row)
        result['questions'] = json.loads(result.pop('questions_json'))
        return result

    def save_attempt(self, ident, answers):
        quiz = self.quiz(ident)
        questions = quiz['questions']
        if len(answers) != len(questions) or any(str(i) not in answers for i in range(len(questions))):
            raise ValueError('Answer every question before saving an attempt')
        for i, question in enumerate(questions):
            labels = [option['label'] for option in question['options']]
            if answers[str(i)] not in labels:
                raise ValueError('An answer is not one of the quiz options')
        correct = sum(answers[str(i)].strip().casefold() == q['correct_answer'].strip().casefold() for i, q in enumerate(questions))
        with closing(get_connection()) as db, db:
            db.execute('INSERT OR IGNORE INTO quiz_attempts(id,quiz_id,answers_json,correct,total) VALUES (?,?,?,?,?)',
                       (new_id(), ident, json.dumps(answers), correct, len(questions)))
            row = db.execute('SELECT * FROM quiz_attempts WHERE quiz_id=?', (ident,)).fetchone()
        return dict(row)

    def progress(self, document_id):
        with closing(get_connection()) as db:
            rows = [dict(r) for r in db.execute('''SELECT a.*, q.questions_json FROM quiz_attempts a
                JOIN study_quizzes q ON q.id=a.quiz_id WHERE q.document_id=? ORDER BY a.rowid DESC''', (document_id,))]
        topics, wrong = {}, []
        for row in rows:
            questions, answers = json.loads(row.pop('questions_json')), json.loads(row.pop('answers_json'))
            for i, q in enumerate(questions):
                topic = q.get('topic') or 'General'
                stats = topics.setdefault(topic, {'topic': topic, 'correct': 0, 'total': 0})
                ok = answers.get(str(i), '').strip().casefold() == q['correct_answer'].strip().casefold()
                stats['total'] += 1
                stats['correct'] += int(ok)
                if not ok:
                    wrong.append(q)
        for stats in topics.values():
            stats['accuracy'] = round(100 * stats['correct'] / stats['total'])
        return {'attempts': rows[:30], 'attempt_count': len(rows),
                'correct': sum(r['correct'] for r in rows), 'total': sum(r['total'] for r in rows),
                'topics': sorted(topics.values(), key=lambda t: t['accuracy']), 'wrong_questions': wrong[:100]}

    def add_flashcards(self, document_id, cards):
        with closing(get_connection()) as db, db:
            before = db.total_changes
            for card in cards:
                db.execute('''INSERT OR IGNORE INTO flashcards
                    (id,document_id,question,answer,source_page,source_chunk_id,source_quote,due_at)
                    VALUES (?,?,?,?,?,?,?,?)''', (new_id(), document_id, card['question'], card.get('answer', card.get('correct_answer')),
                    card.get('source_page'), card.get('source_chunk_id'), card.get('source_quote'), now()))
            return db.total_changes - before

    def flashcards(self, document_id, due_only=False):
        with closing(get_connection()) as db:
            return [dict(r) for r in db.execute('SELECT * FROM flashcards WHERE document_id=?' +
                (' AND due_at<=?' if due_only else '') + ' ORDER BY due_at LIMIT 200',
                (document_id, now()) if due_only else (document_id,))]

    def review_flashcard(self, ident, rating):
        with closing(get_connection()) as db, db:
            row = db.execute('SELECT * FROM flashcards WHERE id=?', (ident,)).fetchone()
            if not row:
                raise KeyError('Flashcard not found')
            old = row['interval_days']
            interval = {'again': 0, 'hard': max(1, round(old * 1.2)),
                        'good': 1 if old == 0 else max(3, round(old * 2.5)),
                        'easy': 3 if old == 0 else max(7, round(old * 3))}[rating]
            due = datetime.now(timezone.utc) + (timedelta(minutes=10) if rating == 'again' else timedelta(days=interval))
            db.execute('UPDATE flashcards SET interval_days=?, repetitions=?, due_at=?, updated_at=? WHERE id=?',
                       (interval, 0 if rating == 'again' else row['repetitions'] + 1, due.isoformat(timespec='seconds'), now(), ident))
            return dict(db.execute('SELECT * FROM flashcards WHERE id=?', (ident,)).fetchone())

    def save_notes(self, document_id, notes, label):
        ident = new_id()
        with closing(get_connection()) as db, db:
            db.execute('INSERT INTO notes_versions(id,document_id,label,notes_json) VALUES (?,?,?,?)',
                       (ident, document_id, label[:120], json.dumps(notes)))
        return ident

    def note_versions(self, document_id):
        with closing(get_connection()) as db:
            return [dict(r) for r in db.execute('SELECT id,label,created_at FROM notes_versions WHERE document_id=? ORDER BY rowid DESC LIMIT 50', (document_id,))]

    def note_version(self, document_id, ident):
        with closing(get_connection()) as db:
            row = db.execute('SELECT notes_json FROM notes_versions WHERE id=? AND document_id=?', (ident, document_id)).fetchone()
            if not row:
                raise KeyError('Notes version not found')
            return json.loads(row[0])
