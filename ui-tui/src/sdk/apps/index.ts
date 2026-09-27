/** Load user-owned widgets only. Demo/reference widgets remain source examples
 *  and visual-test fixtures; registering them in production polluted `/`
 *  completion with commands that do not advance normal work. */
import { loadUserWidgets, watchUserWidgets } from '../userWidgets.js'

void loadUserWidgets()
watchUserWidgets()
